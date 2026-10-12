"""Source request budgets, independent throttles, and safe retry behavior."""
import pytest

from app.jobs.shared.source_requests import RequestPolicy, Response, SourceClient, SourceRequestError


class FakeTime:
    def __init__(self):
        self.value, self.delays = 0, []
    def clock(self):
        return self.value
    def pause(self, delay):
        self.delays.append(delay)
        self.value += delay



def test_source_rate_limits_retry_after_timeouts_and_byte_bounds():
    time = FakeTime()
    responses = iter([Response(429, b"busy", 5), TimeoutError(), Response(200, b'{"ok":true}')])
    calls = []
    def transport(url, **limits):
        calls.append(limits)
        value = next(responses)
        if isinstance(value, Exception):
            raise value
        return value
    client = SourceClient({"fixture": RequestPolicy(minimum_interval_seconds=2)}, transport=transport, clock=time.clock, pause=time.pause)
    assert client.json("fixture", "https://fixture.invalid") == {"ok": True}
    assert len(calls) == 3 and all(call["timeout"] == 20 for call in calls)
    assert time.delays == [5, 2]
    with pytest.raises(SourceRequestError, match="budget"):
        SourceClient({"fixture": RequestPolicy(max_requests=1)}, transport=lambda *a, **k: Response(503, b""), pause=lambda delay: None).get("fixture", "https://fixture.invalid")
    with pytest.raises(SourceRequestError, match="byte"):
        SourceClient({"fixture": RequestPolicy(max_response_bytes=1)}, transport=lambda *a, **k: Response(200, b"xx")).get("fixture", "https://fixture.invalid")



def test_source_policies_are_independent_and_permanent_failures_not_retried():
    time = FakeTime()
    client = SourceClient({"nhl": RequestPolicy(minimum_interval_seconds=3), "mp": RequestPolicy(minimum_interval_seconds=9)},
                          transport=lambda *a, **k: Response(200, b"{}"), clock=time.clock, pause=time.pause)
    client.get("nhl", "https://fixture.invalid")
    client.get("mp", "https://fixture.invalid")
    client.get("nhl", "https://fixture.invalid")
    assert time.delays == [3]
    calls = []
    client.transport = lambda *a, **k: calls.append(1) or Response(404, b"")
    with pytest.raises(SourceRequestError, match="404"):
        client.get("nhl", "https://fixture.invalid")
    assert calls == [1]
    with pytest.raises(ValueError):
        client.get("nhl", "http://fixture.invalid")
    with pytest.raises(ValueError):
        RequestPolicy(timeout_seconds=float("inf"))



def test_source_long_retry_after_defers_instead_of_retrying_before_source_limit():
    time = FakeTime()
    calls = []
    client = SourceClient({"fixture": RequestPolicy()}, transport=lambda *a, **k: calls.append(1) or Response(429, b"", 1000), clock=time.clock, pause=time.pause)
    with pytest.raises(SourceRequestError, match="defer"):
        client.get("fixture", "https://fixture.invalid")
    assert calls == [1] and not time.delays



def test_large_retry_after_protects_subsequent_requests_until_deadline():
    time = FakeTime()
    responses = iter([Response(429, b"", 1000), Response(200, b"{}")])
    client = SourceClient({"fixture": RequestPolicy()}, transport=lambda *a, **k: next(responses), clock=time.clock, pause=time.pause)
    with pytest.raises(SourceRequestError, match="defer"):
        client.get("fixture", "https://fixture.invalid")
    with pytest.raises(SourceRequestError, match="defer"):
        client.get("fixture", "https://fixture.invalid")
    assert client.counts["fixture"] == 1
    time.value = 1000
    assert client.json("fixture", "https://fixture.invalid") == {}



def test_sources_make_progress_independently_while_one_source_waits():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    entered, release = Event(), Event()
    def pause(delay):
        entered.set()
        if not release.wait(timeout=3):
            raise AssertionError("Rate-limit wait did not finish")
    client = SourceClient({"slow": RequestPolicy(minimum_interval_seconds=5), "fast": RequestPolicy(minimum_interval_seconds=0)},
                          transport=lambda *a, **k: Response(200, b"{}"), clock=lambda: 0, pause=pause)
    assert client.get("slow", "https://fixture.invalid") == b"{}"
    with ThreadPoolExecutor(max_workers=2) as pool:
        slow = pool.submit(client.get, "slow", "https://fixture.invalid")
        try:
            assert entered.wait(timeout=2)
            fast = pool.submit(client.get, "fast", "https://fixture.invalid")
            assert fast.result(timeout=1) == b"{}"
        finally:
            release.set()
        assert slow.result(timeout=2) == b"{}"



def test_retry_after_still_applies_when_the_last_allowed_attempt_fails():
    time = FakeTime()
    responses = iter([Response(429, b"", 5), Response(200, b"{}")])
    client = SourceClient({"fixture": RequestPolicy(attempts=1)}, transport=lambda *a, **k: next(responses), clock=time.clock, pause=time.pause)
    with pytest.raises(SourceRequestError, match="bounded retries"):
        client.get("fixture", "https://fixture.invalid")
    assert client.json("fixture", "https://fixture.invalid") == {}
    assert time.delays == [5]

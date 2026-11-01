"""Container readiness and deployed HTTP contract behavior using saved responses."""

import pytest
import asyncio
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError
from urllib.response import addinfourl

from app.shared.tests.fakes import (
    DelayRecorder,
    ReadinessScenario,
    ScriptedRequest,
    StageOutcome,
)
from app.shared.tests.resources import HttpErrorScenario
from backend.database import container_smoke


class TestOwnedHttpErrorResponses:
    cases = (
        pytest.param((None, False), id="handled-status"),
        pytest.param((None, True), id="close-only-failure"),
        pytest.param((RuntimeError, False), id="read-failure"),
        pytest.param((RuntimeError, True), id="read-and-close-failures"),
        pytest.param((asyncio.CancelledError, False), id="cancelled-read"),
        pytest.param((asyncio.CancelledError, True), id="cancelled-read-and-close"),
        pytest.param((KeyboardInterrupt, False), id="interrupted-read"),
        pytest.param((KeyboardInterrupt, True), id="interrupted-read-and-close"),
    )

    @pytest.fixture(params=cases)
    def scenario(self, request, monkeypatch):
        failure_type, close_fails = request.param
        body = BytesIO(b"unavailable_\xff")
        primary = None if failure_type is None else failure_type("read_secret")
        close_failure = OSError("close_secret") if close_fails else None
        events: list[str] = []
        if primary is not None:
            monkeypatch.setattr(
                body,
                "read",
                StageOutcome(result=b"", failure=primary, name="read", events=events),
            )
        if close_failure is not None:
            monkeypatch.setattr(
                body,
                "close",
                StageOutcome(
                    result=None, failure=close_failure, name="close", events=events
                ),
            )
        response = HTTPError(
            "http://container.test/api/health", 503, "unavailable", Message(), body
        )
        monkeypatch.setattr(
            container_smoke, "urlopen", StageOutcome(result=None, failure=response)
        )
        try:
            yield HttpErrorScenario(
                body=body,
                response=response,
                primary=primary,
                close_failure=close_failure,
                events=events,
            )
        finally:
            BytesIO.close(body)

    def test_expected_status_body_and_failure_identity_survive_owned_close(
        self, scenario
    ):
        if scenario.expected_failure is None:
            assert container_smoke.request_json(
                "http://container.test/api/health", 1
            ) == (503, None, "unavailable_\ufffd")
        if scenario.expected_failure is not None:
            with pytest.raises(BaseException) as raised:
                container_smoke.request_json("http://container.test/api/health", 1)
            assert raised.value is scenario.expected_failure
        if scenario.close_failure is None:
            assert scenario.body.closed
        if scenario.close_failure is not None:
            assert scenario.events.count("close") == 1
        if scenario.primary is not None and scenario.close_failure is not None:
            assert (
                scenario.primary.__dict__["tradevalue_cleanup"]
                is scenario.close_failure
            )


class TestOwnedSuccessResponses:
    @pytest.fixture(
        params=[
            pytest.param(b'{"status":"ok"}', id="valid-json"),
            pytest.param(b"not-json", id="decode-failure"),
        ]
    )
    def body(self, request, monkeypatch):
        body = BytesIO(request.param)
        response = addinfourl(body, Message(), "http://container.test/api/health", 200)
        monkeypatch.setattr(container_smoke, "urlopen", StageOutcome(result=response))
        try:
            yield body, request.param
        finally:
            body.close()

    def test_native_success_response_is_closed_after_parsing(self, body):
        response, payload = body
        if payload == b"not-json":
            with pytest.raises(ValueError):
                container_smoke.request_json("http://container.test/api/health", 1)
        if payload != b"not-json":
            assert container_smoke.request_json(
                "http://container.test/api/health", 1
            ) == (200, {"status": "ok"}, '{"status":"ok"}')
        assert response.closed


class TestContainerReadiness:
    success = (
        (200, {"status": "ok"}, "ok"),
        (200, {"status": "ok"}, "ok"),
        (200, {"availableSeasons": [2025], "currentSeason": 2025}, "seasons"),
        (200, [], "teams"),
    )
    expected_urls = (
        "http://container.test/api/health",
        "http://container.test/api/health",
        "http://container.test/api/health",
        "http://container.test/api/seasons",
        "http://container.test/api/teams",
    )

    @pytest.fixture(
        params=[
            pytest.param((503, None, "starting"), id="unhealthy-startup"),
            pytest.param(
                ConnectionResetError("server restarted the connection"),
                id="connection-reset",
            ),
        ]
    )
    def readiness(self, request, monkeypatch):
        scenario = ReadinessScenario(
            request=ScriptedRequest(responses=(request.param, *self.success)),
            sleep=DelayRecorder(),
        )
        monkeypatch.setattr(container_smoke, "request_json", scenario.request)
        monkeypatch.setattr(container_smoke.time, "sleep", scenario.sleep)
        return scenario

    def test_retries_readiness_then_checks_all_routes(self, readiness):
        container_smoke.validate(
            "http://container.test/", attempts=3, delay=0.01, timeout=1
        )
        assert readiness.sleep.delays == [0.01]
        assert tuple(readiness.request.urls) == self.expected_urls

    @pytest.fixture
    def unavailable(self, monkeypatch):
        scenario = ReadinessScenario(
            request=ScriptedRequest(
                responses=((503, None, "database unavailable"),) * 2
            ),
            sleep=DelayRecorder(),
        )
        monkeypatch.setattr(container_smoke, "request_json", scenario.request)
        monkeypatch.setattr(container_smoke.time, "sleep", scenario.sleep)
        return scenario

    def test_reports_readiness_failure_without_running_other_checks(self, unavailable):
        with pytest.raises(RuntimeError, match="did not become healthy"):
            container_smoke.validate(
                "http://container.test", attempts=2, delay=0, timeout=1
            )
        assert unavailable.request.urls == ["http://container.test/api/health"] * 2

    @pytest.fixture(
        params=[
            pytest.param(
                ("/api/health", (200, {"status": "degraded"}, "degraded")),
                id="invalid-health",
            ),
            pytest.param(
                ("/api/seasons", (200, {"availableSeasons": []}, "empty")),
                id="empty-seasons",
            ),
            pytest.param(("/api/teams", (200, {}, "not a list")), id="invalid-teams"),
        ]
    )
    def invalid_contract(self, request, monkeypatch):
        path, invalid_response = request.param
        responses = tuple(
            invalid_response if check_path == path else valid
            for check_path, valid in zip(
                ("/api/health", "/api/seasons", "/api/teams"),
                self.success[1:],
                strict=True,
            )
        )
        saved_request = ScriptedRequest(responses=(self.success[0], *responses))
        monkeypatch.setattr(container_smoke, "request_json", saved_request)
        return path

    def test_rejects_invalid_deployed_contract(self, invalid_contract):
        with pytest.raises(
            RuntimeError, match=f"smoke check failed for {invalid_contract}"
        ):
            container_smoke.validate(
                "http://container.test", attempts=1, delay=0, timeout=1
            )

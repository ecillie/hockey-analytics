"""Bounded synchronous source requests with injectable transport/time for fixtures."""
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import math
import logging
from threading import Lock
from types import MappingProxyType
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .retries import backoff_delay
from app.observability import log_context, log_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    retry_after: float = 0


@dataclass(frozen=True)
class RequestPolicy:
    timeout_seconds: float = 20
    minimum_interval_seconds: float = 1
    attempts: int = 3
    max_response_bytes: int = 8_000_000
    max_requests: int = 10000
    max_retry_delay_seconds: float = 30

    def __post_init__(self):
        for value in (self.timeout_seconds, self.minimum_interval_seconds, self.max_retry_delay_seconds):
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError("Request timing must be finite and nonnegative")
        if not 0 < self.timeout_seconds <= 120 or self.max_retry_delay_seconds > 60 or self.minimum_interval_seconds > 60:
            raise ValueError("Request timeout/delay exceeds bounds")
        for value, upper in ((self.attempts, 10), (self.max_response_bytes, 100_000_000), (self.max_requests, 100000)):
            if type(value) is not int or not 1 <= value <= upper:
                raise ValueError("Request limits must be bounded positive integers")


class SourceRequestError(RuntimeError):
    pass


class SourceHTTPError(SourceRequestError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Source HTTP {status}")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def urllib_transport(url, *, timeout, max_bytes):
    request = Request(url, headers={"User-Agent": "TradeValue-data/1.1", "Accept-Encoding": "identity"})
    try:
        # Redirects would make extra requests outside source-specific rate limits.
        response = build_opener(_NoRedirect()).open(request, timeout=timeout)
    except HTTPError as exc:
        response = exc
    with response:
        body = response.read(max_bytes + 1)
        try:
            delay = float(response.headers.get("Retry-After", "0"))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(response.headers.get("Retry-After", ""))
                delay = max(0, (retry_at - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                delay = 0
        return Response(response.status, body, delay)


class SourceClient:
    def __init__(self, policies, *, transport=urllib_transport, clock=monotonic, pause=sleep):
        if not policies or any(not name or not isinstance(policy, RequestPolicy) for name, policy in policies.items()):
            raise ValueError("Each source requires a request policy")
        self.policies = MappingProxyType(dict(policies))
        self.transport, self.clock, self.pause = transport, clock, pause
        self.next_request, self.counts = {}, {}
        self.locks = {source: Lock() for source in policies}

    def get(self, source, url):
        if source not in self.policies or not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError("Requests require a configured source and HTTPS URL")
        # A wait/retry for one source must not hold other sources' request locks.
        # Serialize this source through its response so Retry-After is observed
        # before a subsequent caller can begin another request.
        with log_context(source=source):
            try:
                with self.locks[source]:
                    return self._get(source, url, self.policies[source])
            except (Exception, KeyboardInterrupt) as exc:
                log_event(logger, "source.failed", level=logging.ERROR, error=exc)
                raise

    def _get(self, source, url, policy):
        for attempt in range(policy.attempts):
            count = self.counts.get(source, 0)
            if count >= policy.max_requests:
                raise SourceRequestError("Source request budget exhausted")
            delay = max(0, self.next_request.get(source, 0) - self.clock())
            if delay > policy.max_retry_delay_seconds:
                raise SourceRequestError("Source rate limit exceeds the bounded wait; defer collection")
            if delay:
                self.pause(delay)
            self.counts[source] = count + 1
            self.next_request[source] = self.clock() + policy.minimum_interval_seconds
            retry_delay = backoff_delay(attempt, policy.max_retry_delay_seconds)
            try:
                response = self.transport(url, timeout=policy.timeout_seconds, max_bytes=policy.max_response_bytes)
            except (URLError, OSError) as exc:
                if attempt + 1 == policy.attempts:
                    raise SourceRequestError("Source request failed after bounded retries") from exc
            else:
                log_event(logger, "source.request", level=logging.DEBUG, attempt=attempt + 1,
                          status_code=response.status)
                if len(response.body) > policy.max_response_bytes:
                    raise SourceRequestError("Source response exceeds byte limit")
                if 200 <= response.status < 300:
                    return response.body
                if response.status not in (408, 429, 500, 502, 503, 504):
                    raise SourceHTTPError(response.status)
                if math.isfinite(response.retry_after):
                    self.next_request[source] = max(self.next_request[source], self.clock() + response.retry_after)
                    if response.retry_after > policy.max_retry_delay_seconds:
                        raise SourceRequestError("Source requested a retry beyond the bounded wait; defer collection")
                    retry_delay = max(retry_delay, response.retry_after)
                if attempt + 1 == policy.attempts:
                    raise SourceRequestError(f"Source HTTP {response.status} after bounded retries")
            self.next_request[source] = max(self.next_request[source], self.clock() + retry_delay)
            log_event(logger, "source.retry", level=logging.WARNING, attempt=attempt + 1,
                      delay_seconds=retry_delay)
            self.pause(retry_delay)
        raise AssertionError("Unreachable")

    def json(self, source, url):
        try:
            return json.loads(self.get(source, url))
        except (ValueError, UnicodeError) as exc:
            log_event(logger, "source.invalid_json", level=logging.ERROR, error=exc, source=source)
            raise SourceRequestError("Source did not return valid JSON") from exc

"""Pure ASGI request diagnostics; no bodies, query strings, or client-supplied IDs."""
import asyncio
import logging
from time import perf_counter
from uuid import uuid4

from app.observability import log_context, log_event

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started, status, error = perf_counter(), None, None
        event = "api.request_completed"

        async def logged_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        with log_context(request_id=uuid4(), component="api", method=scope.get("method", "OTHER")):
            try:
                await self.app(scope, receive, logged_send)
            except BaseException as exc:
                error = exc
                if isinstance(exc, asyncio.CancelledError):
                    event = "api.request_cancelled"
                elif status is None:
                    status = 500
                raise
            finally:
                route = getattr(scope.get("route"), "path", "unmatched")
                level = logging.ERROR if error is not None or (status or 0) >= 500 else logging.WARNING if (status or 0) >= 400 else logging.INFO
                log_event(logger, event, level=level, error=error, route=route,
                          status_code=status, duration_ms=round((perf_counter() - started) * 1000, 3))

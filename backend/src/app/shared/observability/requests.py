"""Streaming ASGI request correlation without task-global mutable context."""

import asyncio
from dataclasses import dataclass
import logging
from time import monotonic_ns
from uuid import uuid4

from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.shared.observability.domain import (
    LogLevel,
    RequestContext,
    RequestFailure,
    RequestOutcome,
)
from app.shared.observability.util import (
    build_request_fields,
    get_request_context as get_request_context,
)


logger = logging.getLogger(__name__)


def choose_summary_level(
    scope: Scope, status: int | None, outcome: RequestOutcome
) -> LogLevel:
    if outcome is RequestOutcome.CANCELLED:
        return LogLevel.DEBUG
    if (
        outcome is RequestOutcome.COMPLETED
        and scope.get("method") in ("GET", "HEAD")
        and scope.get("path") == "/api/health"
        and status is not None
        and 200 <= status < 400
    ):
        return LogLevel.DEBUG
    return LogLevel.INFO


@dataclass(slots=True, kw_only=True, frozen=True)
class RequestLoggingMiddleware:
    app: ASGIApp

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        context = RequestContext(request_id=uuid4().hex, started_ns=monotonic_ns())
        scope["state"] = dict(scope.get("state", {})) | {"logging_context": context}
        status: int | None = None
        response_completed = False
        outcome = RequestOutcome.INCOMPLETE
        logger.debug(
            "Request started",
            extra=build_request_fields(scope, context) | {"event": "request.started"},
        )

        async def capture_send(message: Message) -> None:
            nonlocal status, response_completed
            outgoing = message
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [
                    header
                    for header in message.get("headers", [])
                    if header[0].lower() != b"x-request-id"
                ]
                outgoing = dict(message) | {
                    "headers": headers
                    + [(b"x-request-id", context.request_id.encode("ascii"))]
                }
            await send(outgoing)
            if (
                message["type"] == "http.response.body"
                and message.get("more_body", False) is False
            ):
                response_completed = True

        try:
            await self.app(scope, receive, capture_send)
            outcome = (
                (
                    RequestOutcome.FAILED
                    if status is not None and status >= 500
                    else RequestOutcome.COMPLETED
                )
                if response_completed
                else RequestOutcome.INCOMPLETE
            )
        except BaseException as error:
            outcome = (
                RequestOutcome.CANCELLED
                if isinstance(error, asyncio.CancelledError)
                else RequestOutcome.FAILED
            )
            route = scope.get("route")
            try:
                error.__dict__["tradevalue_request"] = RequestFailure(
                    request_id=context.request_id,
                    method=scope.get("method", "UNKNOWN"),
                    route=route.path if isinstance(route, Route) else None,
                    status=status,
                    duration_ms=context.duration_ms,
                    outcome=outcome,
                    reported=scope["state"].get("request_error_reported")
                    == context.request_id,
                )
            except BaseException:
                pass
            raise
        finally:
            fields = build_request_fields(scope, context) | {
                "event": "request.finished",
                "outcome": outcome.value,
                "duration_ms": context.duration_ms,
            }
            if status is not None:
                fields["status"] = status
            logger.log(
                choose_summary_level(scope, status, outcome),
                "Request finished",
                extra=fields,
            )

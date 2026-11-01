"""Safe lifespan protocol events while retaining the original ASGI failure."""

import asyncio
from dataclasses import dataclass, field
import json
import logging
from typing import Literal

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.shared.cleanup import retain_cleanup_failure
from app.shared.observability.domain import LoggingSettings
from app.shared.observability.formatting import collect_exceptions
from app.shared.observability.schemas import LifecycleEvent, LifecycleReport
from app.shared.observability.util import read_cleanup_failure


logger = logging.getLogger(__name__)

type LifecyclePhase = Literal["startup", "shutdown"]


def serialize_lifecycle_failure(
    error: BaseException, phase: LifecyclePhase, settings: LoggingSettings
) -> str:
    event: LifecycleEvent = (
        "service.startup_failed" if phase == "startup" else "service.shutdown_failed"
    )
    cleanup = read_cleanup_failure(error)
    if isinstance(error, asyncio.CancelledError) and (
        cleanup is None or isinstance(cleanup, asyncio.CancelledError)
    ):
        event = (
            "service.startup_cancelled"
            if phase == "startup"
            else "service.shutdown_cancelled"
        )
    payload: dict[str, object] = {
        "event": event,
        "exceptions": (),
        "exceptions_truncated": True,
    }
    try:
        exceptions = collect_exceptions(error, settings.limits)
        report = LifecycleReport.model_validate(
            payload
            | {
                "exceptions": exceptions.items,
                "exceptions_truncated": exceptions.truncated,
            }
        )
        encoded = report.model_dump_json()
    except Exception:
        encoded = json.dumps(payload, separators=(",", ":"))
    if (
        len(encoded.encode("utf-8")) + len("tradevalue.lifecycle ")
        > settings.limits.record_bytes
    ):
        encoded = json.dumps(payload, separators=(",", ":"))
    return "tradevalue.lifecycle " + encoded


@dataclass(slots=True, kw_only=True, frozen=True)
class LifecycleLoggingMiddleware:
    app: ASGIApp
    settings: LoggingSettings = field(default_factory=LoggingSettings)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "lifespan":
            await self.app(scope, receive, send)
            return
        failure_phase: LifecyclePhase | None = None

        async def capture_send(message: Message) -> None:
            nonlocal failure_phase
            if message["type"] in (
                "lifespan.startup.failed",
                "lifespan.shutdown.failed",
            ):
                failure_phase = (
                    "startup"
                    if message["type"] == "lifespan.startup.failed"
                    else "shutdown"
                )
                return
            await send(message)
            if message["type"] == "lifespan.startup.complete":
                logger.info("API ready", extra={"event": "service.ready"})
            if message["type"] == "lifespan.shutdown.complete":
                logger.info("API stopped", extra={"event": "service.stopped"})

        try:
            await self.app(scope, receive, capture_send)
        except BaseException as error:
            if failure_phase is not None:
                message: Message = {
                    "type": f"lifespan.{failure_phase}.failed",
                    "message": serialize_lifecycle_failure(
                        error, failure_phase, self.settings
                    ),
                }
                try:
                    await send(message)
                except BaseException as delivery:
                    retain_cleanup_failure(error, delivery)
            raise

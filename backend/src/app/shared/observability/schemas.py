"""Validated safe diagnostics carried by the ASGI lifespan failure protocol."""

import logging
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, ValidationError

from app.shared.observability.domain import LogLevel


type SafeIdentifier = Annotated[
    str, StringConstraints(pattern=r"^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$", max_length=256)
]
type FrameLine = Annotated[int, Field(ge=0, le=1_000_000_000)]


class StackFrame(BaseModel, frozen=True, extra="forbid"):
    module: SafeIdentifier
    function: SafeIdentifier
    line: FrameLine


type StackFrames = Annotated[tuple[StackFrame, ...], Field(max_length=64)]


class ExceptionSnapshot(BaseModel, frozen=True, extra="forbid"):
    type: SafeIdentifier
    frames: StackFrames
    frames_truncated: bool


type ExceptionSnapshots = Annotated[tuple[ExceptionSnapshot, ...], Field(max_length=8)]
type LifecycleEvent = Literal[
    "service.startup_failed",
    "service.shutdown_failed",
    "service.startup_cancelled",
    "service.shutdown_cancelled",
]


class LifecycleReport(BaseModel, frozen=True, extra="forbid"):
    event: LifecycleEvent
    exceptions: ExceptionSnapshots
    exceptions_truncated: bool

    @property
    def level(self) -> LogLevel:
        if self.event.endswith("cancelled"):
            return LogLevel.DEBUG
        return (
            LogLevel.CRITICAL
            if self.event == "service.startup_failed"
            else LogLevel.ERROR
        )


def read_lifecycle_report(
    record: logging.LogRecord, logger_name: str = "uvicorn.error"
) -> LifecycleReport | None:
    prefix = "tradevalue.lifecycle "
    if (
        record.name != logger_name
        or type(record.msg) is not str
        or len(record.msg) > 8192
        or not record.msg.startswith(prefix)
    ):
        return None
    try:
        return LifecycleReport.model_validate_json(
            record.msg[len(prefix) :], strict=True
        )
    except ValidationError:
        return None

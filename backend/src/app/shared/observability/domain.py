"""Immutable diagnostic settings independent of database and environment loading."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum, auto
from time import monotonic_ns
from typing import Literal
from app.shared.observability.errors import LoggingSettingsError


class LogLevel(IntEnum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class LogFormat(StrEnum):
    JSON = auto()
    TEXT = auto()


class RequestOutcome(StrEnum):
    COMPLETED = auto()
    INCOMPLETE = auto()
    FAILED = auto()
    CANCELLED = auto()


class CommandOutcome(StrEnum):
    COMPLETED = auto()
    FAILED = auto()
    INCOMPLETE = auto()
    CANCELLED = auto()


@dataclass(slots=True, kw_only=True, frozen=True)
class InvocationContext:
    invocation_id: str
    source: str
    started_ns: int

    @property
    def fields(self) -> dict[str, object]:
        return {"invocation_id": self.invocation_id, "source": self.source}

    @property
    def duration_ms(self) -> float:
        return (monotonic_ns() - self.started_ns) / 1_000_000


@dataclass(slots=True, kw_only=True, frozen=True)
class RequestContext:
    request_id: str
    started_ns: int

    @property
    def duration_ms(self) -> float:
        return (monotonic_ns() - self.started_ns) / 1_000_000


type FailedRequestOutcome = Literal[RequestOutcome.FAILED, RequestOutcome.CANCELLED]


@dataclass(slots=True, kw_only=True, frozen=True)
class RequestFailure:
    request_id: str
    method: str
    route: str | None
    status: int | None
    duration_ms: float
    outcome: FailedRequestOutcome
    reported: bool = False

    @property
    def level(self) -> LogLevel:
        return (
            LogLevel.DEBUG
            if self.outcome is RequestOutcome.CANCELLED
            else LogLevel.ERROR
        )

    @property
    def event(self) -> str:
        return (
            "request.cancelled"
            if self.outcome is RequestOutcome.CANCELLED
            else "request.failed"
        )

    @property
    def fields(self) -> dict[str, object]:
        values: dict[str, object] = {
            "request_id": self.request_id,
            "method": self.method,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "outcome": self.outcome.value,
        }
        if self.route is not None:
            values["route"] = self.route
        return values


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordLimits:
    record_bytes: int = 8192
    string_characters: int = 256
    stack_frames: int = 12
    exception_depth: int = 4


@dataclass(slots=True, kw_only=True, frozen=True)
class LoggingSettings:
    level: LogLevel = LogLevel.INFO
    format: LogFormat = LogFormat.JSON
    environment: str | None = None
    release: str | None = None
    limits: RecordLimits = field(default_factory=RecordLimits)


def read_logging_settings(values: Mapping[str, str]) -> LoggingSettings:
    try:
        level = LogLevel[values.get("LOG_LEVEL", "INFO").strip().upper()]
    except KeyError:
        raise LoggingSettingsError(
            field="LOG_LEVEL", choices=", ".join(LogLevel.__members__)
        ) from None
    try:
        format = LogFormat(values.get("LOG_FORMAT", "json").strip().lower())
    except ValueError:
        raise LoggingSettingsError(field="LOG_FORMAT", choices="json, text") from None
    environment = values.get("ENV", "").strip().lower()
    release = values.get("VERCEL_GIT_COMMIT_SHA", "")
    return LoggingSettings(
        level=level,
        format=format,
        environment=environment if environment in ("dev", "nonprod", "prod") else None,
        release=release
        if len(release) == 40 and all(c in "0123456789abcdef" for c in release)
        else None,
    )

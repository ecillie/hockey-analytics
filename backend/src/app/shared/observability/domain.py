"""Immutable diagnostic settings independent of database and environment loading."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum, auto
from time import monotonic_ns


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


@dataclass(slots=True, kw_only=True, frozen=True)
class RequestContext:
    request_id: str
    started_ns: int

    @property
    def duration_ms(self) -> float:
        return (monotonic_ns() - self.started_ns) / 1_000_000


class LoggingSettingsError(ValueError):
    def __init__(self, *, field: str, choices: str) -> None:
        super().__init__(f"{field} must be one of: {choices}")
        self.field = field
        self.choices = choices


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

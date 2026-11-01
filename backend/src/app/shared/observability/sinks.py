"""Safe stderr delivery without recursive logging or raw-record error reports."""

from dataclasses import dataclass
import logging
from typing import Protocol, runtime_checkable

from app.shared.observability.domain import LogFormat, LoggingSettings
from app.shared.observability.formatting import SafeFormatter, render_failure_diagnostic
from app.shared.observability.policy import find_record_limits_violation


@runtime_checkable
class DiagnosticStream(Protocol):
    def write(self, value: str, /) -> int: ...

    def flush(self) -> None: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class SafeStream:
    stream: DiagnosticStream
    format: LogFormat = LogFormat.JSON

    def write(self, value: str) -> int:
        try:
            self.stream.write(value)
        except Exception:
            try:
                self.stream.write(
                    render_failure_diagnostic("logging.sink_failed", self.format) + "\n"
                )
            except Exception:
                pass
        return len(value)

    def flush(self) -> None:
        try:
            self.stream.flush()
        except Exception:
            pass


def build_diagnostic_handler(
    settings: LoggingSettings, stream: DiagnosticStream
) -> logging.Handler:
    if violation := find_record_limits_violation(settings.limits):
        raise violation
    handler = logging.StreamHandler(SafeStream(stream=stream, format=settings.format))
    handler.setLevel(settings.level)
    handler.setFormatter(SafeFormatter(settings=settings))
    return handler

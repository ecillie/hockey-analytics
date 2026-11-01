"""Bounded diagnostics that never interpolate arbitrary messages or exception values."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import logging
import math
import re
from types import TracebackType
from typing import Literal

from app.shared.observability.domain import (
    LogFormat,
    LogLevel,
    LoggingSettings,
    RecordLimits,
)
from app.shared.observability.policy import find_record_limits_violation


type DiagnosticFields = dict[str, object]
type DiagnosticFailure = Literal["logging.format_failed", "logging.sink_failed"]


@dataclass(slots=True, kw_only=True, frozen=True)
class DiagnosticCollection:
    items: tuple[DiagnosticFields, ...]
    truncated: bool


def safe_identifier(value: object, limits: RecordLimits) -> str:
    if type(value) is not str:
        return "unsupported"
    if len(value) > limits.string_characters:
        return "truncated"
    if re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]*", value) is None:
        return "invalid"
    return value


def collect_stack(
    traceback: TracebackType | None, limits: RecordLimits
) -> DiagnosticCollection:
    frames: list[DiagnosticFields] = []
    while traceback is not None and len(frames) < limits.stack_frames:
        frame = traceback.tb_frame
        frames.append(
            {
                "module": safe_identifier(frame.f_globals.get("__name__"), limits),
                "function": safe_identifier(frame.f_code.co_name, limits),
                "line": traceback.tb_lineno,
            }
        )
        traceback = traceback.tb_next
    return DiagnosticCollection(items=tuple(frames), truncated=traceback is not None)


def collect_exceptions(
    error: BaseException, limits: RecordLimits
) -> DiagnosticCollection:
    errors: list[DiagnosticFields] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while (
        current is not None
        and id(current) not in seen
        and len(errors) < limits.exception_depth
    ):
        seen.add(id(current))
        stack = collect_stack(current.__traceback__, limits)
        errors.append(
            {
                "type": safe_identifier(type(current).__name__, limits),
                "frames": stack.items,
                "frames_truncated": stack.truncated,
            }
        )
        following = current.__cause__
        if following is None and not current.__suppress_context__:
            following = current.__context__
        current = following
    return DiagnosticCollection(items=tuple(errors), truncated=current is not None)


def collect_context(
    record: logging.LogRecord, limits: RecordLimits
) -> DiagnosticFields:
    identifiers = (
        "request_id",
        "invocation_id",
        "stage",
        "source",
        "outcome",
        "method",
    )
    numbers = (
        "run_id",
        "season",
        "status",
        "duration_ms",
        "attempt",
        "fetched",
        "validated",
        "attempted",
        "committed",
        "rolled_back",
    )
    context: DiagnosticFields = {}
    if "route" in record.__dict__:
        route = record.__dict__["route"]
        context["route"] = (
            route
            if type(route) is str
            and len(route) <= limits.string_characters
            and re.fullmatch(r"/[a-zA-Z0-9_{}:./-]*", route) is not None
            else "invalid"
        )
    for key in identifiers:
        if key in record.__dict__:
            context[key] = safe_identifier(record.__dict__[key], limits)
    for key in numbers:
        value = record.__dict__.get(key)
        if (
            isinstance(value, (int, float))
            and type(value) in (int, float)
            and abs(value) <= 1e15
            and math.isfinite(value)
        ):
            context[key] = value
    return context


def encode_diagnostic(payload: DiagnosticFields, format: LogFormat) -> str:
    rendered = json.dumps(
        payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")
    )
    return "event " + rendered if format is LogFormat.TEXT else rendered


def render_failure_diagnostic(event: DiagnosticFailure, format: LogFormat) -> str:
    return encode_diagnostic(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": "ERROR",
            "event": event,
            "logger": "logging.safe",
            "message": event.replace(".", " ").replace("_", " "),
        },
        format,
    )


def is_application_record(record: logging.LogRecord) -> bool:
    return type(record.name) is str and any(
        record.name == namespace or record.name.startswith(namespace + ".")
        for namespace in ("app", "backend", "ml", "__main__")
    )


def render_bounded_diagnostic(
    payload: DiagnosticFields, settings: LoggingSettings
) -> str:
    rendered = encode_diagnostic(payload, settings.format)
    if len(rendered.encode("utf-8")) + 1 <= settings.limits.record_bytes:
        return rendered
    payload = payload | {"truncated": True, "message": "Diagnostic truncated"}
    removable = iter(
        (
            "exceptions",
            "exceptions_truncated",
            "route",
            "source",
            "stage",
            "outcome",
            "method",
            "fetched",
            "validated",
            "attempted",
            "committed",
            "rolled_back",
            "attempt",
            "duration_ms",
            "season",
            "status",
            "run_id",
            "invocation_id",
            "request_id",
        )
    )
    rendered = encode_diagnostic(payload, settings.format)
    while (
        len(rendered.encode("utf-8")) + 1 > settings.limits.record_bytes
        and (key := next(removable, None)) is not None
    ):
        payload.pop(key, None)
        rendered = encode_diagnostic(payload, settings.format)
    return rendered


@dataclass(slots=True, kw_only=True, frozen=True)
class SafeFormatter(logging.Formatter):
    settings: LoggingSettings = field(default_factory=LoggingSettings)

    def format(self, record: logging.LogRecord) -> str:
        try:
            return self.render_record(record)
        except Exception:
            return render_failure_diagnostic(
                "logging.format_failed", self.settings.format
            )

    def render_record(self, record: logging.LogRecord) -> str:
        limits = self.settings.limits
        if violation := find_record_limits_violation(limits):
            raise violation
        application_record = is_application_record(record)
        event = safe_identifier(
            record.__dict__.get("event", "application.record")
            if application_record
            else "dependency.record",
            limits,
        )
        payload: DiagnosticFields = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "severity": LogLevel(record.levelno).name,
            "event": event,
            "logger": safe_identifier(record.name, limits),
            "message": event.replace(".", " "),
        }
        if self.settings.environment in ("dev", "nonprod", "prod"):
            payload["environment"] = self.settings.environment
        release = self.settings.release
        if type(release) is str and re.fullmatch(r"[0-9a-f]{40}", release) is not None:
            payload["release"] = release
        if application_record:
            payload.update(collect_context(record, limits))
        if isinstance(record.exc_info, tuple) and record.exc_info[1] is not None:
            exceptions = collect_exceptions(record.exc_info[1], limits)
            payload["exceptions"] = exceptions.items
            payload["exceptions_truncated"] = exceptions.truncated
        return render_bounded_diagnostic(payload, self.settings)

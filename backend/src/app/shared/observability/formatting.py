"""Bounded diagnostics that never interpolate arbitrary messages or exception values."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import logging
import math
import re
from collections.abc import Mapping
from types import TracebackType
from typing import Literal

from app.shared.observability.domain import (
    LogFormat,
    LogLevel,
    LoggingSettings,
    RecordLimits,
)
from app.shared.observability.policy import find_record_limits_violation
from app.shared.observability.schemas import LifecycleReport, read_lifecycle_report
from app.shared.observability.util import read_cleanup_failure, read_request_failure


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
    cleanup = read_cleanup_failure(error)
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
        if following is None and cleanup is not None and id(cleanup) not in seen:
            following, cleanup = cleanup, None
        current = following
    return DiagnosticCollection(items=tuple(errors), truncated=current is not None)


def collect_context(
    record: logging.LogRecord, limits: RecordLimits
) -> DiagnosticFields:
    return sanitize_context(record.__dict__, limits)


def sanitize_context(
    values: Mapping[str, object], limits: RecordLimits
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
    if "route" in values:
        route = values["route"]
        context["route"] = (
            route
            if type(route) is str
            and len(route) <= limits.string_characters
            and re.fullmatch(r"/[a-zA-Z0-9_{}:./-]*", route) is not None
            else "invalid"
        )
    for key in identifiers:
        if key in values:
            context[key] = safe_identifier(values[key], limits)
    for key in numbers:
        value = values.get(key)
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


def render_failure_diagnostic(
    event: DiagnosticFailure, format: LogFormat, severity: LogLevel = LogLevel.ERROR
) -> str:
    timestamp = "1970-01-01T00:00:00+00:00"
    unavailable = "true"
    try:
        candidate = datetime.now(UTC).isoformat()
        if (
            type(candidate) is str
            and len(candidate) <= 40
            and re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?\+00:00",
                candidate,
            )
            is not None
        ):
            timestamp, unavailable = candidate, "false"
    except Exception:
        pass
    event = (
        "logging.sink_failed"
        if type(event) is str and event == "logging.sink_failed"
        else "logging.format_failed"
    )
    severity = severity if isinstance(severity, LogLevel) else LogLevel.ERROR
    message = (
        "Diagnostic delivery failed"
        if event == "logging.sink_failed"
        else "Diagnostic formatting failed"
    )
    rendered = (
        f'{{"timestamp":"{timestamp}","timestamp_unavailable":{unavailable},'
        f'"severity":"{severity.name}","event":"{event}",'
        f'"logger":"logging.safe","message":"{message}"}}'
    )
    return "event " + rendered if format is LogFormat.TEXT else rendered


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
            severity = LogLevel.ERROR
            try:
                severity = LogLevel(max(record.levelno, logging.ERROR))
            except Exception:
                pass
            return render_failure_diagnostic(
                "logging.format_failed", self.settings.format, severity
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
        if failure := read_request_failure(record):
            payload.update(sanitize_context(failure.fields, limits))
            payload.update(
                {
                    "event": failure.event,
                    "severity": failure.level.name,
                    "message": failure.event.replace(".", " ").capitalize(),
                }
            )
        report = record.__dict__.get("lifecycle_report")
        report = (
            report
            if isinstance(report, LifecycleReport)
            else read_lifecycle_report(record)
        )
        if report is not None:
            payload.update(
                {
                    "event": report.event,
                    "severity": report.level.name,
                    "logger": "app.shared.observability.lifecycle",
                    "message": report.event.replace(".", " ").replace("_", " "),
                    "exceptions": tuple(
                        item.model_dump() for item in report.exceptions
                    ),
                    "exceptions_truncated": report.exceptions_truncated,
                }
            )
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

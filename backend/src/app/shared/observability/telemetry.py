"""Application Insights export built from the same allowlisted fields as stderr."""

from collections.abc import Mapping
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
import logging

from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogRecordExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.context import Context
from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer, use_span
from starlette.routing import Route
from starlette.types import Scope

from app.shared.observability.domain import (
    LogLevel,
    LoggingSettings,
    RequestOutcome,
    TelemetrySettings,
)
from app.shared.observability.formatting import (
    DiagnosticFields,
    SafeFormatter,
    is_application_record,
)


TELEMETRY_HANDLER_NAME = "tradevalue.telemetry"
TELEMETRY_NAMESPACES = (
    "app",
    "backend",
    "ml",
    "__main__",
    "sqlalchemy",
    "uvicorn.error",
)
SEVERITY_NUMBERS = {
    LogLevel.DEBUG: SeverityNumber.DEBUG,
    LogLevel.INFO: SeverityNumber.INFO,
    LogLevel.WARNING: SeverityNumber.WARN,
    LogLevel.ERROR: SeverityNumber.ERROR,
    LogLevel.CRITICAL: SeverityNumber.FATAL,
}


@dataclass(slots=True, kw_only=True, frozen=True)
class TelemetryExporters:
    spans: SpanExporter
    logs: LogRecordExporter


def build_azure_exporters(settings: TelemetrySettings) -> TelemetryExporters:
    from azure.monitor.opentelemetry.exporter import (
        AzureMonitorLogExporter,
        AzureMonitorTraceExporter,
    )

    options = {
        "connection_string": settings.connection_string,
        "disable_offline_storage": True,
    }
    return TelemetryExporters(
        spans=AzureMonitorTraceExporter(**options),
        logs=AzureMonitorLogExporter(**options),
    )


def format_exception_stack(exceptions: object) -> str:
    lines: list[str] = []
    for item in exceptions if isinstance(exceptions, tuple) else ():
        lines.append(str(item["type"]))
        lines.extend(
            f"  at {frame['module']}.{frame['function']} line {frame['line']}"
            for frame in item["frames"]
        )
        if item["frames_truncated"]:
            lines.append("  ...")
    return "\n".join(lines)


def build_log_attributes(
    payload: DiagnosticFields,
) -> dict[str, str | int | float | bool]:
    attributes: dict[str, str | int | float | bool] = {
        key: value
        for key, value in payload.items()
        if key not in ("timestamp", "message", "exceptions")
        and isinstance(value, (str, int, float, bool))
    }
    exceptions = payload.get("exceptions")
    if isinstance(exceptions, tuple) and len(exceptions) > 0:
        attributes["exception.type"] = str(exceptions[0]["type"])
        attributes["exception.stacktrace"] = format_exception_stack(exceptions)
    return attributes


@dataclass(slots=True, kw_only=True, frozen=True)
class SeveritySpanProcessor(SpanProcessor):
    """Drops request spans whose summary severity is below the export threshold."""

    delegate: SpanProcessor
    minimum_level: LogLevel = LogLevel.INFO

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        self.delegate.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        severity = (span.attributes or {}).get("severity")
        if (
            isinstance(severity, str)
            and severity in LogLevel.__members__
            and LogLevel[severity] < self.minimum_level
        ):
            return
        self.delegate.on_end(span)

    def shutdown(self) -> None:
        self.delegate.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.delegate.force_flush(timeout_millis)


class TelemetryHandler(logging.Handler):
    """Exports sanitized diagnostics; delivery faults never reach the caller."""

    def __init__(
        self,
        *,
        settings: LoggingSettings,
        logger_provider: LoggerProvider,
        tracer_provider: TracerProvider,
    ) -> None:
        super().__init__(settings.level)
        self.formatter = SafeFormatter(settings=settings)
        self.logger_provider = logger_provider
        self.tracer_provider = tracer_provider

    @property
    def tracer(self) -> Tracer:
        return self.tracer_provider.get_tracer("app.shared.observability.requests")

    def emit(self, record: logging.LogRecord) -> None:
        if not is_application_record(record) and record.levelno < logging.WARNING:
            return
        try:
            assert isinstance(self.formatter, SafeFormatter)
            payload = self.formatter.build_payload(record)
            severity = LogLevel[str(payload["severity"])]
            self.logger_provider.get_logger(str(payload["logger"])).emit(
                timestamp=int(record.created * 1_000_000_000),
                severity_number=SEVERITY_NUMBERS[severity],
                severity_text=severity.name,
                body=str(payload["message"]),
                attributes=build_log_attributes(payload),
            )
        except Exception:
            pass

    def handleError(self, record: logging.LogRecord) -> None:
        pass

    def flush(self) -> None:
        try:
            self.tracer_provider.force_flush()
            self.logger_provider.force_flush()
        except Exception:
            pass

    def shutdown(self) -> None:
        for namespace in TELEMETRY_NAMESPACES:
            logging.getLogger(namespace).removeHandler(self)
        self.close()
        self.tracer_provider.shutdown()
        self.logger_provider.shutdown()


def configure_telemetry(
    logging_settings: LoggingSettings,
    telemetry_settings: TelemetrySettings,
    *,
    exporters: TelemetryExporters | None = None,
) -> TelemetryHandler | None:
    if not telemetry_settings.enabled:
        return None
    existing = logging.getHandlerByName(TELEMETRY_HANDLER_NAME)
    if isinstance(existing, TelemetryHandler):
        return existing
    exporters = (
        build_azure_exporters(telemetry_settings) if exporters is None else exporters
    )
    attributes: dict[str, str] = {"service.name": "tradevalue-api"}
    if logging_settings.environment is not None:
        attributes["deployment.environment.name"] = logging_settings.environment
    if logging_settings.release is not None:
        attributes["service.version"] = logging_settings.release
    resource = Resource.create(attributes)
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        SeveritySpanProcessor(
            delegate=BatchSpanProcessor(exporters.spans),
            minimum_level=logging_settings.level,
        )
    )
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporters.logs))
    handler = TelemetryHandler(
        settings=logging_settings,
        logger_provider=logger_provider,
        tracer_provider=tracer_provider,
    )
    handler.set_name(TELEMETRY_HANDLER_NAME)
    for namespace in TELEMETRY_NAMESPACES:
        logging.getLogger(namespace).addHandler(handler)
    return handler


@dataclass(slots=True, kw_only=True)
class RequestTelemetry:
    """Holds the tracer that the API lifespan installs after middleware is built."""

    tracer: Tracer | None = field(default=None, repr=False)

    def start(self, scope: Scope) -> Span | None:
        if self.tracer is None:
            return None
        method = str(scope.get("method", "UNKNOWN"))
        span = self.tracer.start_span(
            method,
            kind=SpanKind.SERVER,
            attributes={"http.request.method": method},
            record_exception=False,
            set_status_on_exception=False,
        )
        return span if isinstance(span, Span) else None

    @staticmethod
    def activate(span: Span | None) -> AbstractContextManager[object]:
        if span is None:
            return nullcontext()
        return use_span(
            span,
            end_on_exit=False,
            record_exception=False,
            set_status_on_exception=False,
        )

    @staticmethod
    def finish(
        span: Span,
        scope: Scope,
        fields: Mapping[str, object],
        *,
        level: LogLevel,
        outcome: RequestOutcome,
    ) -> None:
        try:
            RequestTelemetry.describe(span, scope, fields, level=level, outcome=outcome)
            span.end()
        except Exception:
            pass

    @staticmethod
    def describe(
        span: Span,
        scope: Scope,
        fields: Mapping[str, object],
        *,
        level: LogLevel,
        outcome: RequestOutcome,
    ) -> None:
        route = scope.get("route")
        if isinstance(route, Route):
            span.update_name(f"{scope.get('method', 'UNKNOWN')} {route.path}")
            span.set_attribute("http.route", route.path)
        status = fields.get("status")
        if type(status) is int:
            span.set_attribute("http.response.status_code", status)
        span.set_attribute("request_id", str(fields["request_id"]))
        span.set_attribute("outcome", outcome.value)
        span.set_attribute("severity", level.name)
        span.set_status(
            Status(StatusCode.ERROR)
            if outcome is RequestOutcome.FAILED
            else Status(StatusCode.OK)
        )

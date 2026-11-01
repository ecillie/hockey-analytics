"""Process-owned logging installation for command main and approved API startup."""

import logging
import sys
from dataclasses import dataclass
from types import TracebackType
from time import monotonic_ns
from uuid import uuid4
from starlette.types import Scope

from app.shared.observability.domain import (
    CommandOutcome,
    InvocationContext,
    LogLevel,
    LoggingSettings,
    DiagnosticContext,
    TransactionOutcome,
)
from app.shared.observability.formatting import SafeFormatter
from app.shared.observability.errors import (
    LoggingOwnershipError,
    LoggingConfigurationConflictError,
)
from app.shared.observability.policy import (
    ReportedRequestFilter,
    RequestFailureFilter,
    LifecycleReportFilter,
)
from app.shared.observability.util import (
    build_request_fields,
    get_request_context,
    is_expected_cancellation,
)
from app.shared.cleanup import retain_cleanup_failure
from app.shared.observability.sinks import (
    DiagnosticStream,
    SafeStream,
    build_diagnostic_handler,
)


logger = logging.getLogger(__name__)


def report_transaction_outcome(
    context: DiagnosticContext | None,
    outcome: TransactionOutcome,
    *,
    failure: BaseException | None = None,
) -> None:
    if context is None:
        return
    level = (
        LogLevel.DEBUG
        if failure is not None and is_expected_cancellation(failure)
        else outcome.level
    )
    logger.log(
        level,
        "Transaction outcome",
        extra=context.fields | {"event": outcome.event, "outcome": outcome.value},
    )


def start_command(source: str) -> InvocationContext:
    context = InvocationContext(
        invocation_id=uuid4().hex, source=source, started_ns=monotonic_ns()
    )
    logger.info("Command started", extra=context.fields | {"event": "command.started"})
    return context


def finish_command(context: InvocationContext, outcome: CommandOutcome) -> None:
    logger.log(
        LogLevel.DEBUG if outcome is CommandOutcome.CANCELLED else LogLevel.INFO,
        "Command finished",
        extra=context.fields
        | {
            "event": "command.finished",
            "outcome": outcome.value,
            "duration_ms": context.duration_ms,
        },
    )


def retain_lifespan_cleanup(primary: BaseException, cleanup: BaseException) -> None:
    retain_cleanup_failure(primary, cleanup)


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandExceptionHook:
    context: InvocationContext

    def __call__(
        self,
        kind: type[BaseException],
        error: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        cancelled = is_expected_cancellation(error)
        logger.log(
            LogLevel.DEBUG if cancelled else LogLevel.ERROR,
            "Command stopped",
            exc_info=(kind, error, traceback),
            extra=self.context.fields
            | {"event": "command.cancelled" if cancelled else "command.failed"},
        )
        finish_command(
            self.context,
            CommandOutcome.CANCELLED if cancelled else CommandOutcome.FAILED,
        )


def configure_command_exceptions(context: InvocationContext) -> None:
    sys.excepthook = CommandExceptionHook(context=context)


def report_request_error(scope: Scope, error: Exception) -> None:
    fields: dict[str, object] = {"event": "request.failed"}
    context = get_request_context(scope)
    if context is not None:
        fields.update(build_request_fields(scope, context))
    logger.error("Request failed", exc_info=error, extra=fields)
    if context is not None:
        scope["state"]["request_error_reported"] = context.request_id


def configure_logging(
    settings: LoggingSettings, *, stream: DiagnosticStream | None = None
) -> logging.Handler:
    stream = sys.stderr if stream is None else stream
    name = "tradevalue.diagnostics"
    handler = logging.getHandlerByName(name)
    if handler is None:
        handler = build_diagnostic_handler(settings, stream)
        handler.set_name(name)
    if not isinstance(handler, logging.StreamHandler) or not isinstance(
        handler.formatter, SafeFormatter
    ):
        raise LoggingOwnershipError(name=name)
    if handler.formatter.settings != settings:
        raise LoggingConfigurationConflictError()
    handler.setStream(
        SafeStream(stream=stream, format=settings.format, minimum_level=settings.level)
    )
    application_names = ("app", "backend", "ml", "__main__")
    dependency_names = (
        "sqlalchemy",
        "httpx",
        "httpcore",
        "urllib3",
        "requests",
        "alembic",
    )
    for namespace in application_names + dependency_names:
        target = logging.getLogger(namespace)
        target.setLevel(
            settings.level
            if namespace in application_names
            else max(LogLevel.WARNING, settings.level)
        )
        target.addHandler(handler)
        target.propagate = False
    return handler


def configure_api_host_logging(
    settings: LoggingSettings, handler: logging.Handler
) -> None:
    host = logging.getLogger("uvicorn")
    errors = logging.getLogger("uvicorn.error")
    if len(host.handlers) == 0:
        host.addHandler(handler)
    for existing in tuple(host.handlers) + tuple(errors.handlers):
        existing.setLevel(settings.level)
        existing.setFormatter(SafeFormatter(settings=settings))
        if isinstance(existing, logging.StreamHandler) and not isinstance(
            existing.stream, SafeStream
        ):
            existing.setStream(
                SafeStream(
                    stream=existing.stream,
                    format=settings.format,
                    minimum_level=settings.level,
                )
            )
    host.setLevel(settings.level)
    host.propagate = False
    errors.setLevel(min(logging.ERROR, settings.level))
    errors.propagate = len(errors.handlers) == 0
    if not any(isinstance(item, ReportedRequestFilter) for item in errors.filters):
        errors.addFilter(ReportedRequestFilter())
    if not any(isinstance(item, RequestFailureFilter) for item in errors.filters):
        errors.addFilter(RequestFailureFilter())
    if not any(isinstance(item, LifecycleReportFilter) for item in errors.filters):
        errors.addFilter(LifecycleReportFilter())
    logging.getLogger("uvicorn.access").disabled = True

"""Process-owned logging installation for command main and approved API startup."""

import logging
import sys

from app.shared.observability.domain import LogLevel, LoggingSettings
from app.shared.observability.formatting import SafeFormatter
from app.shared.observability.sinks import (
    DiagnosticStream,
    SafeStream,
    build_diagnostic_handler,
)


class LoggingOwnershipError(RuntimeError):
    def __init__(self, *, name: str) -> None:
        super().__init__(
            f"Diagnostic handler name {name} is already owned by another configuration"
        )
        self.name = name


class LoggingConfigurationConflictError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "Logging settings changed within one process; restart to apply new settings"
        )


def configure_logging(
    settings: LoggingSettings, *, stream: DiagnosticStream | None = None
) -> None:
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
    handler.setStream(SafeStream(stream=stream, format=settings.format))
    application_names = ("app", "backend", "ml", "__main__")
    dependency_names = ("sqlalchemy", "httpx", "httpcore", "urllib3", "requests")
    for namespace in application_names + dependency_names:
        target = logging.getLogger(namespace)
        target.setLevel(
            settings.level
            if namespace in application_names
            else max(LogLevel.WARNING, settings.level)
        )
        target.addHandler(handler)
        target.propagate = False

"""Safe ingestion progress; translated exceptions remain owned by commands."""

from collections.abc import Mapping
import logging

from app.shared.observability.domain import InvocationContext, LogLevel
from app.ScriptingFiles.FullDataScript.tracking.domain import IngestionContext


logger = logging.getLogger(__name__)


def build_ingestion_context(
    invocation: InvocationContext | None, *, source: str, stage: str
) -> IngestionContext | None:
    if invocation is None:
        return None
    return IngestionContext(invocation=invocation, source=source, stage=stage)


def report_ingestion_progress(
    context: IngestionContext | None,
    *,
    event: str,
    values: Mapping[str, int | float | str] | None = None,
    level: LogLevel = LogLevel.INFO,
) -> None:
    if context is None:
        return
    fields = context.fields | {"event": event}
    if values is not None:
        fields.update(values)
    logger.log(level, "Ingestion progress", extra=fields)

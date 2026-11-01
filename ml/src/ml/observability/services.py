"""Aggregate ML progress without datasets, artifact paths or model payloads."""

from collections.abc import Mapping
import logging

from app.shared.observability.domain import InvocationContext, LogLevel


logger = logging.getLogger(__name__)


def report_ml_progress(
    context: InvocationContext | None,
    *,
    event: str,
    stage: str,
    values: Mapping[str, int | float] | None = None,
    level: LogLevel = LogLevel.INFO,
) -> None:
    if context is None:
        return
    fields = context.fields | {"event": event, "stage": stage}
    if values is not None:
        fields.update(values)
    logger.log(level, "ML progress", extra=fields)

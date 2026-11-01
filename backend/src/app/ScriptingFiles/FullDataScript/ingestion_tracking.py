"""Compatibility decorator for durable ingestion lifecycle tracking."""

from collections.abc import Callable, Mapping
from functools import wraps
from dataclasses import replace
from typing import Protocol, cast, runtime_checkable

from app.ScriptingFiles.FullDataScript.tracking.errors import (
    ConcurrentIngestionError as ConcurrentIngestionError,
)
from app.ScriptingFiles.FullDataScript.tracking.repository import (
    build_advisory_lock_key,
)
from app.ScriptingFiles.FullDataScript.tracking.domain import IngestionContext
from app.ScriptingFiles.FullDataScript.tracking.errors import IngestionBatchError
from app.ScriptingFiles.FullDataScript.tracking.services import (
    report_ingestion_progress,
)
from app.ScriptingFiles.FullDataScript.tracking.util import collect_ingestion_counts
from app.shared.observability.domain import LogLevel
from app.shared.observability.util import is_expected_cancellation
from app.shared.cleanup import retain_cleanup_failure
from app.ScriptingFiles.FullDataScript.tracking.repository import (
    open_ingestion_run,
    IngestionRun,
)


@runtime_checkable
class NamedFunction[**P, R](Protocol):
    __name__: str

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...


def tracked_ingestion[**P, R: Mapping[str, object]](
    source_code: str, job_name: str | None = None
) -> Callable[[NamedFunction[P, R]], Callable[P, R]]:
    def decorate(function: NamedFunction[P, R]) -> Callable[P, R]:
        resolved_job_name = function.__name__ if job_name is None else job_name

        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            with open_ingestion_run(
                source_code=source_code, job_name=resolved_job_name
            ) as run:
                supplied = kwargs.get("context")
                context = None
                if isinstance(supplied, IngestionContext):
                    context = replace(
                        supplied,
                        run_id=run.run_id,
                        source=source_code,
                        stage=resolved_job_name,
                    )
                    cast(dict[str, object], kwargs)["context"] = context
                report_ingestion_progress(context, event="ingestion.started")
                summary: R | None = None
                try:
                    summary = function(*args, **kwargs)
                    run.succeed(summary)
                except BaseException as primary:
                    report_ingestion_failure(run, primary)
                    progress = (
                        collect_ingestion_counts(primary.committed_summary)
                        if isinstance(primary, IngestionBatchError)
                        else collect_ingestion_counts(summary)
                        if summary is not None
                        else {}
                    )
                    cancelled = is_expected_cancellation(primary)
                    report_ingestion_progress(
                        context,
                        event="ingestion.finished",
                        level=LogLevel.DEBUG if cancelled else LogLevel.INFO,
                        values=progress
                        | {
                            "outcome": "cancelled" if cancelled else "failed",
                            "duration_ms": context.duration_ms
                            if context is not None
                            else 0,
                        },
                    )
                    raise
                report_ingestion_progress(
                    context,
                    event="ingestion.finished",
                    values=collect_ingestion_counts(summary)
                    | {
                        "outcome": "completed",
                        "duration_ms": context.duration_ms
                        if context is not None
                        else 0,
                    },
                )
                return summary

        return wrapped

    return decorate


def report_ingestion_failure(run: IngestionRun, primary: BaseException) -> None:
    try:
        run.fail(primary)
    except BaseException as reporting:
        retain_cleanup_failure(primary, reporting)


advisory_lock_key = build_advisory_lock_key

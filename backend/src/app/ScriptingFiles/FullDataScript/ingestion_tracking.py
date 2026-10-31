"""Compatibility decorator for durable ingestion lifecycle tracking."""

from collections.abc import Callable, Mapping
from functools import wraps
from typing import Protocol, runtime_checkable

from app.ScriptingFiles.FullDataScript.tracking.errors import (
    ConcurrentIngestionError as ConcurrentIngestionError,
)
from app.ScriptingFiles.FullDataScript.tracking.repository import (
    advisory_lock_key as advisory_lock_key,
)
from app.ScriptingFiles.FullDataScript.tracking.repository import (
    open_ingestion_run,
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
                try:
                    summary = function(*args, **kwargs)
                    run.succeed(summary)
                except BaseException as primary:
                    try:
                        run.fail(primary)
                    except BaseException as reporting:
                        primary.add_note(
                            f"Ingestion failure reporting also failed: {reporting!r}"
                        )
                    raise
                return summary

        return wrapped

    return decorate

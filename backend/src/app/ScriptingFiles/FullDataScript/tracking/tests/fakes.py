"""Owned run records and injected work failures without PostgreSQL."""

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field

from app.ScriptingFiles.FullDataScript.tracking.domain import IngestionContext
from app.ScriptingFiles.FullDataScript.tracking.repository import IngestionRun


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordingRun:
    events: list[str]
    run_id: int = 17
    reporting_failure: BaseException | None = None
    completion_failure: BaseException | None = None

    def succeed(self, summary: Mapping[str, object]) -> None:
        self.events.append("succeeded")
        if self.completion_failure is not None:
            raise self.completion_failure

    def fail(self, failure: BaseException) -> None:
        self.events.append("failed")
        if self.reporting_failure is not None:
            raise self.reporting_failure


@dataclass(slots=True, kw_only=True, frozen=True)
class TrackingScenario:
    failure: BaseException | None = None
    reporting_failure: BaseException | None = None
    completion_failure: BaseException | None = None
    contexts: list[IngestionContext | None] = field(default_factory=list)
    events: list[str] = field(default_factory=list)

    @contextmanager
    def open_run(self, **kwargs: object) -> Generator[IngestionRun]:
        try:
            yield RecordingRun(
                events=self.events,
                reporting_failure=self.reporting_failure,
                completion_failure=self.completion_failure,
            )
        finally:
            self.events.append("closed")

    def ingest(self, *, context: IngestionContext | None = None) -> dict[str, int]:
        self.contexts.append(context)
        self.events.append("work")
        if self.failure is not None:
            raise self.failure
        return {"records_read": 8, "records_created": 3, "records_updated": 2}

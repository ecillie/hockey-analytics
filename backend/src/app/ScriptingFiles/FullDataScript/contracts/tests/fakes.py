"""Instrumented session ownership for saved profile responses."""

from _thread import LockType
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Barrier, Lock
from typing import Self

from app.ScriptingFiles.FullDataScript.contracts.domain import Candidate, ProfileResult
from app.ScriptingFiles.FullDataScript.contracts.options import (
    HistoricalContractOptions,
)
from app.ScriptingFiles.FullDataScript.contracts.repository import ContractRepository
from app.ScriptingFiles.FullDataScript.contracts.tests.fixtures import SavedResponse


@dataclass(slots=True, kw_only=True, frozen=True)
class ConcurrentProfileSession:
    response: SavedResponse
    barrier: Barrier

    def get(self, url: str, *, timeout: float) -> SavedResponse:
        self.barrier.wait(timeout=5)
        return self.response


@dataclass(slots=True, kw_only=True, frozen=True)
class ProfileSessionProbe:
    response: SavedResponse
    barrier: Barrier
    opened: list[ConcurrentProfileSession] = field(default_factory=list)
    closed: list[ConcurrentProfileSession] = field(default_factory=list)
    lock: LockType = field(default_factory=Lock)

    @contextmanager
    def open_session(self) -> Generator[ConcurrentProfileSession]:
        session = ConcurrentProfileSession(response=self.response, barrier=self.barrier)
        with self.lock:
            self.opened.append(session)
        try:
            yield session
        finally:
            with self.lock:
                self.closed.append(session)


def reject_resource_access(*args: object, **kwargs: object) -> None:
    raise AssertionError("invalid options reached a resource boundary")


@dataclass(slots=True, kw_only=True, frozen=True)
class FailingCleanup:
    failure: RuntimeError
    calls: list[str]
    name: str

    def __call__(self) -> None:
        self.calls.append(self.name)
        raise self.failure


@dataclass(slots=True, kw_only=True, frozen=True)
class FailingRun:
    reporting_failure: RuntimeError

    def succeed(self, summary: object) -> None:
        raise self.reporting_failure

    def fail(self, failure: BaseException) -> None:
        raise self.reporting_failure


@dataclass(slots=True, kw_only=True, frozen=True)
class FailedTrackingScenario:
    primary: RuntimeError
    reporting: RuntimeError

    @contextmanager
    def open_run(self, **kwargs: object) -> Generator[FailingRun]:
        yield FailingRun(reporting_failure=self.reporting)

    def ingest(self) -> dict[str, int]:
        raise self.primary


@dataclass(slots=True, kw_only=True, frozen=True)
class EmptyContractRepository:
    candidates: tuple[Candidate, ...] = ()
    summary: Mapping[str, int] = field(default_factory=dict)

    def select_candidates(
        self, options: HistoricalContractOptions
    ) -> tuple[Candidate, ...]:
        return self.candidates

    def persist_batch(
        self,
        candidates: tuple[Candidate, ...],
        results: tuple[ProfileResult, ...],
        options: HistoricalContractOptions,
        *,
        dry_run: bool,
    ) -> Mapping[str, int]:
        return self.summary

    def coverage_counts(
        self, options: HistoricalContractOptions
    ) -> Mapping[str, object]:
        return self.summary

    @contextmanager
    def open_repository(self) -> Generator[ContractRepository]:
        yield self


@dataclass(slots=True, kw_only=True, frozen=True)
class LockObservedSession:
    response: SavedResponse
    lock: LockType
    calls: list[str] = field(default_factory=list)
    closures: list[bool] = field(default_factory=list)

    def get(self, url: str, *, timeout: float) -> SavedResponse:
        assert self.lock.locked()
        self.calls.append(url)
        return self.response

    def close(self) -> None:
        self.closures.append(True)


@dataclass(slots=True, kw_only=True, frozen=True)
class FailedControlConnection:
    failure: RuntimeError
    closures: list[bool] = field(default_factory=list)

    def cursor(self) -> None:
        raise self.failure

    def close(self) -> None:
        self.closures.append(True)

    def open_connection(self) -> Self:
        return self


@dataclass(slots=True, kw_only=True, frozen=True)
class ActiveFixtureSession:
    index_html: str
    profile_html: str
    barrier: Barrier

    def get(self, url: str, *, timeout: float) -> SavedResponse:
        if url.endswith("/players/active"):
            return SavedResponse(
                status_code=200, headers={}, text=self.index_html, url=url
            )
        self.barrier.wait(timeout=5)
        slug = url.rsplit("/", 1)[-1]
        return SavedResponse(
            status_code=200,
            headers={},
            text=self.profile_html.replace("fixture-player", slug),
            url=url,
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class ActiveSessionProbe:
    index_html: str
    profile_html: str
    barrier: Barrier
    opened: list[ActiveFixtureSession] = field(default_factory=list)
    closed: list[ActiveFixtureSession] = field(default_factory=list)
    lock: LockType = field(default_factory=Lock)

    @contextmanager
    def open_session(self) -> Generator[ActiveFixtureSession]:
        session = ActiveFixtureSession(
            index_html=self.index_html,
            profile_html=self.profile_html,
            barrier=self.barrier,
        )
        with self.lock:
            self.opened.append(session)
        try:
            yield session
        finally:
            with self.lock:
                self.closed.append(session)

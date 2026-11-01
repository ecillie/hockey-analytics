"""Frozen collaborator bundles for source-stage scenarios."""

from dataclasses import dataclass
from collections.abc import Callable
from contextlib import AbstractContextManager
import requests
from sqlalchemy import Engine
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import MoneyPuckSummary
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.domain import (
    MoneyPuckSnapshot,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.domain import (
    NhlStatsSnapshot,
)
from typing import Literal, TypedDict
from pydantic import TypeAdapter
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import DataQualityReport
from app.ScriptingFiles.FullDataScript.source_ingestion.errors import (
    IngestionValidationError,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.tests.fakes import (
    MemorySourceClient,
    ManagedSession,
)
from app.ScriptingFiles.FullDataScript.roster_status.tests.fakes import FixedRosterFeed
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.repository import (
    PostgresMoneyPuckRepository,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.repository import (
    PostgresNhlStatsRepository,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class RepositoryStage[S, R]:
    service: S
    repository: R


@dataclass(slots=True, kw_only=True, frozen=True)
class ClientStage[S, R, C]:
    service: S
    repository: R
    client: C


@dataclass(slots=True, kw_only=True, frozen=True)
class WorkerStage[S, R, F]:
    service: S
    repository: R
    factory: F
    invalid: bool


@dataclass(slots=True, kw_only=True, frozen=True)
class BorrowedTransport[F, S]:
    factory: F
    session: S


@dataclass(slots=True, kw_only=True, frozen=True)
class PaginationScenario:
    client: MemorySourceClient
    maximum_pages: int


@dataclass(slots=True, kw_only=True, frozen=True)
class SessionScenario:
    session: ManagedSession
    failing: bool


@dataclass(slots=True, kw_only=True, frozen=True)
class SessionCloseProbe:
    session: requests.Session
    native_close: Callable[[], None]
    cleanup: BaseException | None
    closed: list[bool]

    def close(self) -> None:
        self.closed.append(True)
        self.native_close()
        if self.cleanup is not None:
            raise self.cleanup


@dataclass(slots=True, kw_only=True, frozen=True)
class SessionSetupScenario:
    resource: SessionCloseProbe
    primary: BaseException
    cause: ValueError


type SessionOwnerFactory = Callable[[], AbstractContextManager[object]]


@dataclass(slots=True, kw_only=True, frozen=True)
class SessionLifetimeScenario:
    factory: SessionOwnerFactory
    resource: SessionCloseProbe
    primary: BaseException | None
    cause: ValueError
    fail_during_entry: bool

    @property
    def expected_failure(self) -> BaseException | None:
        return self.primary if self.primary is not None else self.resource.cleanup


def exercise_session_owner(scenario: SessionLifetimeScenario) -> None:
    with scenario.factory():
        if scenario.primary is not None and scenario.fail_during_entry is False:
            raise scenario.primary


@dataclass(slots=True, kw_only=True, frozen=True)
class ValidationBoundary:
    adapter: TypeAdapter[object]
    failure_type: type[ValueError]


@dataclass(slots=True, kw_only=True, frozen=True)
class QualityScenario:
    report: DataQualityReport
    minimum_rows: int
    maximum_duplicate_ratio: float
    error: type[IngestionValidationError] | None


@dataclass(slots=True, kw_only=True, frozen=True)
class IdentityPersistence:
    moneypuck: MoneyPuckSnapshot
    nhl: NhlStatsSnapshot
    expected_puck_hash: str
    expected_nhl_hash: str
    advanced_table: str
    basic_table: str


@dataclass(slots=True, kw_only=True, frozen=True)
class IdentityRepositories:
    moneypuck: PostgresMoneyPuckRepository
    nhl: PostgresNhlStatsRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class RosterFeedScenario:
    nhl: FixedRosterFeed
    ahl: FixedRosterFeed


type RetainedStage = Literal["capwages", "historical", "moneypuck"]


@dataclass(slots=True, kw_only=True, frozen=True)
class RetainedStageScenario:
    failed_stage: RetainedStage
    events: list[str]


@dataclass(slots=True, kw_only=True, frozen=True)
class RetainedMoneyPuckScenario:
    database: Engine
    first: MoneyPuckSummary
    second: MoneyPuckSummary


class MoneyPuckFixtureOptions(TypedDict):
    expected_seasons: tuple[int, ...]
    minimum_rows_per_kind: int
    maximum_duplicate_ratio: float

"""Frozen collaborator bundles for source-stage scenarios."""

from dataclasses import dataclass
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.domain import (
    MoneyPuckSnapshot,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.domain import (
    NhlStatsSnapshot,
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
class IdentityPersistence:
    moneypuck: MoneyPuckSnapshot
    nhl: NhlStatsSnapshot
    expected_puck_hash: str
    expected_nhl_hash: str
    advanced_table: str
    basic_table: str

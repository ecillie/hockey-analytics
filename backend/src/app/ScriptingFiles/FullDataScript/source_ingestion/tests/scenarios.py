"""Frozen collaborator bundles for source-stage scenarios."""

from dataclasses import dataclass


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

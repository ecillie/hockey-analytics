"""In-memory source clients and repositories for stage behavior tests."""

from collections.abc import Mapping, Generator
from contextlib import contextmanager
from threading import Barrier, Lock
from _thread import LockType
from typing import Self

from app.ScriptingFiles.FullDataScript.source_ingestion.http import (
    SourceClient,
    SourceResponse,
    SourceHttpOptions,
)
from dataclasses import dataclass, field

from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    MoneyPuckSummary,
    NhlStatsSummary,
    RosterSummary,
    ScheduleSummary,
    WriteCounts,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.domain import (
    MoneyPuckSnapshot,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.domain import (
    NhlStatsSnapshot,
    NhlRosterSnapshot,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.schedule.domain import (
    ScheduleSnapshot,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class MemorySourceClient:
    pages: Mapping[tuple[str, int], object] = field(default_factory=dict)
    csv_files: Mapping[str, str] = field(default_factory=dict)
    calls: list[tuple[str, int]] = field(default_factory=list)

    def get_json(self, url: str, *, timeout=30, params=None) -> object:
        start = 0 if params is None else int(params.get("start", 0))
        self.calls.append((url, start))
        result = self.pages[(url, start)]
        if isinstance(result, Exception):
            raise result
        return result

    def get_csv(self, url: str, *, timeout=60) -> str:
        self.calls.append((url, 0))
        return self.csv_files[url]

    def __len__(self) -> int:
        return len(self.calls)


@dataclass(slots=True, kw_only=True, frozen=True)
class MemoryMoneyPuckRepository:
    snapshots: list[MoneyPuckSnapshot] = field(default_factory=list)

    def persist(self, snapshot: MoneyPuckSnapshot) -> MoneyPuckSummary:
        self.snapshots.append(snapshot)
        skaters = sum(row.kind == "skater" for row in snapshot.rows)
        return MoneyPuckSummary(
            players=len({row.external_id for row in snapshot.rows}),
            skater=skaters,
            goalie=len(snapshot.rows) - skaters,
            counts=WriteCounts(
                records_read=sum(r.records_read for r in snapshot.quality),
                records_created=len(snapshot.rows),
                records_updated=0,
                records_skipped=sum(r.duplicate_records for r in snapshot.quality),
            ),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class MemoryNhlStatsRepository:
    snapshots: list[NhlStatsSnapshot] = field(default_factory=list)

    def persist(self, snapshot: NhlStatsSnapshot) -> NhlStatsSummary:
        self.snapshots.append(snapshot)
        skaters = sum(row.kind == "skater" for row in snapshot.rows)
        return NhlStatsSummary(
            skater=skaters,
            goalie=len(snapshot.rows) - skaters,
            team_stints=0,
            counts=WriteCounts(
                records_read=len(snapshot.rows),
                records_created=len(snapshot.rows),
                records_updated=0,
                records_skipped=0,
            ),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class MemoryRosterRepository:
    snapshots: list[NhlRosterSnapshot] = field(default_factory=list)

    def persist(self, snapshot: NhlRosterSnapshot) -> RosterSummary:
        self.snapshots.append(snapshot)
        return RosterSummary(
            teams=len(snapshot.teams), active_players=len(snapshot.players)
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class MemoryScheduleRepository:
    snapshots: list[ScheduleSnapshot] = field(default_factory=list)

    def persist(self, snapshot: ScheduleSnapshot) -> ScheduleSummary:
        self.snapshots.append(snapshot)
        return ScheduleSummary(
            games=len(snapshot.games),
            counts=WriteCounts(
                records_read=snapshot.records_read,
                records_created=len(snapshot.games),
                records_updated=0,
                records_skipped=snapshot.records_read - len(snapshot.games),
            ),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class OwnedClientFactory:
    client: SourceClient
    barrier: Barrier
    lock: LockType = field(default_factory=Lock)
    state: dict[str, int] = field(default_factory=dict)

    @contextmanager
    def __call__(self) -> Generator[SourceClient]:
        with self.lock:
            self.state["opened"] = self.state.get("opened", 0) + 1
            self.state["active"] = self.state.get("active", 0) + 1
            self.state["maximum"] = max(
                self.state.get("maximum", 0), self.state["active"]
            )
        try:
            self.barrier.wait(timeout=5)
            yield self.client
        finally:
            with self.lock:
                self.state["active"] -= 1
                self.state["closed"] = self.state.get("closed", 0) + 1


@dataclass(slots=True, kw_only=True, frozen=True)
class ManagedResponse:
    text: str = "csv-content"
    payload: object = None
    failure: Exception | None = None

    def raise_for_status(self) -> None:
        if self.failure is not None:
            raise self.failure

    def json(self) -> object:
        return self.payload


@dataclass(slots=True, kw_only=True, frozen=True)
class ManagedSession:
    response: SourceResponse
    required_lock: LockType | None = None
    opened: list[bool] = field(default_factory=list)
    closed: list[bool] = field(default_factory=list)
    calls: list[tuple[str, float]] = field(default_factory=list)

    def get(
        self, url: str, *, timeout: float, params: Mapping[str, str | int] | None = None
    ) -> SourceResponse:
        if self.required_lock is not None:
            assert self.required_lock.locked()
        self.calls.append((url, timeout))
        return self.response

    def __enter__(self) -> Self:
        self.opened.append(True)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.closed.append(True)


@dataclass(slots=True, kw_only=True, frozen=True)
class ManagedSessionFactory:
    session: ManagedSession

    def __call__(self, options: SourceHttpOptions | None = None) -> ManagedSession:
        return self.session

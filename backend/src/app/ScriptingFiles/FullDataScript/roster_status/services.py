"""Coordinate roster feeds and transaction-owned persistence."""

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable
from app.ScriptingFiles.FullDataScript.tracking.domain import IngestionContext
from app.ScriptingFiles.FullDataScript.tracking.services import (
    report_ingestion_progress,
)
from app.shared.observability.domain import LogLevel

from app.ScriptingFiles.FullDataScript.roster_status.domain import (
    FetchResult,
    RosterEvidence,
    RosterStatus,
    SyncSummary,
)
from app.ScriptingFiles.FullDataScript.roster_status.policy import classify_player
from app.ScriptingFiles.FullDataScript.roster_status.repository import RosterRepository
from app.ScriptingFiles.FullDataScript.roster_status.util import match_ahl_players


@runtime_checkable
class RosterFeed(Protocol):
    def fetch_current_rosters(self) -> FetchResult: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class RosterStatusService:
    repository: RosterRepository
    nhl_service: RosterFeed
    ahl_service: RosterFeed
    context: IngestionContext | None = None

    def sync(self, as_of: date | None = None) -> SyncSummary:
        as_of = date.today() if as_of is None else as_of
        players = self.repository.load_players()
        ltir_player_ids = self.repository.load_active_ltir_player_ids(as_of)
        nhl_result = self.nhl_service.fetch_current_rosters()
        ahl_result = self.ahl_service.fetch_current_rosters()
        report_ingestion_progress(
            self.context,
            event="ingestion.feed_received",
            values={
                "source": "nhl",
                "fetched": len(nhl_result.items),
                "outcome": "completed" if nhl_result.complete else "incomplete",
            },
            level=LogLevel.DEBUG,
        )
        report_ingestion_progress(
            self.context,
            event="ingestion.feed_received",
            values={
                "source": "ahl",
                "fetched": len(ahl_result.items),
                "outcome": "completed" if ahl_result.complete else "incomplete",
            },
            level=LogLevel.DEBUG,
        )
        ahl_matches = match_ahl_players(players, ahl_result.items)
        self.repository.save_ahl_external_ids(
            (player_id, match.external_id, match.full_name)
            for player_id, match in ahl_matches.items()
        )
        evidence = RosterEvidence(
            ltir_player_ids=ltir_player_ids,
            nhl_external_ids=frozenset(
                player.external_id for player in nhl_result.items
            ),
            ahl_player_ids=frozenset(ahl_matches),
            nhl_complete=nhl_result.complete,
            ahl_complete=ahl_result.complete,
        )
        decisions = {player.id: classify_player(player, evidence) for player in players}
        updates = {
            player_id: status
            for player_id, status in decisions.items()
            if status is not None
        }
        self.repository.bulk_update_statuses(updates)
        counts = {
            status: sum(value == status for value in updates.values())
            for status in RosterStatus
        }
        return SyncSummary(
            statuses_updated=len(updates),
            active_count=counts[RosterStatus.ACTIVE],
            minors_count=counts[RosterStatus.MINORS],
            ltir_count=counts[RosterStatus.LTIR],
            unknown_count=counts[RosterStatus.UNKNOWN],
            preserved_count=len(players) - len(updates),
            nhl_complete=nhl_result.complete,
            ahl_complete=ahl_result.complete,
            errors=nhl_result.errors + ahl_result.errors,
        )

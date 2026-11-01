"""Atomic MoneyPuck identity and advanced-stat persistence."""

from dataclasses import dataclass
from app.database import open_database_cursor
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    MoneyPuckSummary,
    Player,
    PlayerKind,
    StatRow,
    WriteCounts,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import select_stat_layout
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.domain import (
    MoneyPuckSnapshot,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.repository import (
    TransactionFactory,
    load_source_ids,
    ensure_teams,
    upsert_player,
    build_stat_values,
    write_stats,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class PostgresMoneyPuckRepository:
    transaction: TransactionFactory

    def persist(self, snapshot: MoneyPuckSnapshot) -> MoneyPuckSummary:
        with (
            self.transaction() as connection,
            open_database_cursor(connection) as cursor,
        ):
            source_id = load_source_ids(cursor)["moneypuck"]
            team_ids = ensure_teams(
                cursor, (team for row in snapshot.rows for team in row.teams)
            )
            latest: dict[str, StatRow] = {}
            for row in snapshot.rows:
                if (
                    row.external_id not in latest
                    or row.season >= latest[row.external_id].season
                ):
                    latest[row.external_id] = row
            player_ids = {
                external_id: upsert_player(
                    cursor,
                    source_id,
                    Player(
                        external_id=external_id, name=row.name, position=row.position
                    ),
                )
                for external_id, row in latest.items()
            }
            counts: dict[PlayerKind, int] = {}
            created = updated = 0
            for kind in PlayerKind:
                incoming = (
                    build_stat_values(
                        row,
                        player_ids[row.external_id],
                        team_ids,
                        source_id,
                        advanced=True,
                    )
                    for row in snapshot.rows
                    if row.kind == kind
                )
                by_grain = {tuple(value[:6]): value for value in incoming}
                values = tuple(by_grain.values())
                new, changed = write_stats(
                    cursor, select_stat_layout(kind, advanced=True), source_id, values
                )
                created += new
                updated += changed
                counts[kind] = len(values)
        return MoneyPuckSummary(
            players=len(player_ids),
            skater=counts[PlayerKind.SKATER],
            goalie=counts[PlayerKind.GOALIE],
            counts=WriteCounts(
                records_read=sum(report.records_read for report in snapshot.quality),
                records_created=created,
                records_updated=updated,
                records_skipped=sum(
                    report.duplicate_records for report in snapshot.quality
                ),
            ),
        )

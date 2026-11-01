"""Atomic NHL identity, traditional-stat, and roster persistence."""

from dataclasses import dataclass
from app.database import open_database_cursor
from psycopg2.extras import execute_values

from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    NhlStatsSummary,
    PlayerKind,
    RosterSummary,
    WriteCounts,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import select_stat_layout
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.domain import (
    NhlRosterSnapshot,
    NhlStatsSnapshot,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.repository import (
    TransactionFactory,
    load_source_ids,
    ensure_teams,
    ensure_seasons,
    upsert_player,
    link_external_id,
    resolve_nhl_player,
    build_stat_values,
    write_stats,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.util import split_name


@dataclass(slots=True, kw_only=True, frozen=True)
class PostgresNhlStatsRepository:
    transaction: TransactionFactory

    def persist(self, snapshot: NhlStatsSnapshot) -> NhlStatsSummary:
        with (
            self.transaction() as connection,
            open_database_cursor(connection) as cursor,
        ):
            sources = load_source_ids(cursor)
            nhl_id, moneypuck_id = sources["nhl"], sources["moneypuck"]
            team_ids = ensure_teams(
                cursor, (team for row in snapshot.rows for team in row.teams)
            )
            first_profiles = {}
            for row in snapshot.rows:
                first_profiles.setdefault(row.external_id, row)
            player_cache = {
                external_id: resolve_nhl_player(cursor, nhl_id, moneypuck_id, row)
                for external_id, row in first_profiles.items()
            }
            final_teams = {
                (player_cache[row.external_id], row.season): team_ids[row.teams[-1]]
                for row in snapshot.rows
                if row.game_type == 2 and len(row.teams) > 0
            }
            counts: dict[PlayerKind, int] = {}
            created = updated = 0
            for kind in PlayerKind:
                incoming = (
                    build_stat_values(
                        row,
                        player_cache[row.external_id],
                        team_ids,
                        nhl_id,
                        advanced=False,
                    )
                    for row in snapshot.rows
                    if row.kind == kind
                )
                by_grain = {tuple(value[:6]): value for value in incoming}
                values = tuple(by_grain.values())
                new, changed = write_stats(
                    cursor, select_stat_layout(kind, advanced=False), nhl_id, values
                )
                created += new
                updated += changed
                counts[kind] = len(values)
            if len(final_teams) > 0:
                execute_values(
                    cursor,
                    "INSERT INTO player_team_stints (player_id,season_start_year,team_id) VALUES %s ON CONFLICT DO NOTHING",
                    [
                        (player_id, season, team_id)
                        for (player_id, season), team_id in sorted(final_teams.items())
                    ],
                    page_size=1000,
                )
        written = sum(counts.values())
        return NhlStatsSummary(
            skater=counts[PlayerKind.SKATER],
            goalie=counts[PlayerKind.GOALIE],
            team_stints=len(final_teams),
            counts=WriteCounts(
                records_read=len(snapshot.rows),
                records_created=created,
                records_updated=updated,
                records_skipped=len(snapshot.rows) - written,
            ),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class PostgresNhlRosterRepository:
    transaction: TransactionFactory

    def persist(self, snapshot: NhlRosterSnapshot) -> RosterSummary:
        with (
            self.transaction() as connection,
            open_database_cursor(connection) as cursor,
        ):
            sources = load_source_ids(cursor)
            moneypuck_id, nhl_id = sources["moneypuck"], sources["nhl"]
            ensure_seasons(cursor, (snapshot.season,))
            team_ids = ensure_teams(
                cursor,
                (team.abbreviation for team in snapshot.teams),
                {team.abbreviation: team for team in snapshot.teams},
            )
            for row in snapshot.players:
                player = row.player
                cursor.execute(
                    "SELECT player_id FROM player_external_ids WHERE source_id=%s AND external_id=%s",
                    (moneypuck_id, player.external_id),
                )
                found = cursor.fetchone()
                if found is not None:
                    player_id = found[0]
                    link_external_id(
                        cursor, player_id, nhl_id, player.external_id, player.name
                    )
                    cursor.execute(
                        """UPDATE players SET first_name=%s,last_name=%s,birth_date=%s,primary_position=%s,
                        shoots_catches=%s,nationality=%s,active=TRUE,updated_at=CURRENT_TIMESTAMP WHERE id=%s""",
                        (
                            *split_name(player.name),
                            player.birth_date,
                            player.position,
                            player.shoots_catches,
                            row.birth_country,
                            player_id,
                        ),
                    )
                if found is None:
                    player_id = upsert_player(cursor, nhl_id, player)
                cursor.execute(
                    """INSERT INTO player_team_stints (player_id,season_start_year,team_id,roster_status)
                    VALUES (%s,%s,%s,'ACTIVE') ON CONFLICT DO NOTHING""",
                    (player_id, snapshot.season, team_ids[row.team]),
                )
        return RosterSummary(
            teams=len(snapshot.teams), active_players=len(snapshot.players)
        )

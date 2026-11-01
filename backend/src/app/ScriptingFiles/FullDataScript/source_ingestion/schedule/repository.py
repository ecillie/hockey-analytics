"""Atomic, retain-missing schedule upserts."""

from dataclasses import dataclass
from app.database import open_database_cursor
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    ScheduleSummary,
    WriteCounts,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.repository import (
    TransactionFactory,
    ensure_teams,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.schedule.domain import (
    ScheduleSnapshot,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class PostgresScheduleRepository:
    transaction: TransactionFactory

    def persist(self, snapshot: ScheduleSnapshot) -> ScheduleSummary:
        with (
            self.transaction() as connection,
            open_database_cursor(connection) as cursor,
        ):
            cursor.execute(
                "SELECT count(*) FROM games WHERE nhl_game_id = ANY(%s)",
                ([game.external_id for game in snapshot.games],),
            )
            incoming = cursor.fetchone()
            assert incoming is not None
            incoming_before = incoming[0]
            team_ids = ensure_teams(
                cursor,
                (
                    team
                    for game in snapshot.games
                    for team in (game.away_team, game.home_team)
                ),
            )
            for game in snapshot.games:
                cursor.execute(
                    """INSERT INTO games (nhl_game_id,season_start_year,game_type,game_date,start_time_utc,
                    away_team_id,home_team_id,venue,game_state,away_score,home_score,last_synced_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                    ON CONFLICT (nhl_game_id) DO UPDATE SET game_state=EXCLUDED.game_state,
                    away_score=EXCLUDED.away_score,home_score=EXCLUDED.home_score,last_synced_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP""",
                    (
                        game.external_id,
                        snapshot.season,
                        2,
                        game.game_date,
                        game.start_time_utc,
                        team_ids[game.away_team],
                        team_ids[game.home_team],
                        game.venue,
                        game.game_state,
                        game.away_score,
                        game.home_score,
                    ),
                )
        created = len(snapshot.games) - incoming_before
        return ScheduleSummary(
            games=len(snapshot.games),
            counts=WriteCounts(
                records_read=snapshot.records_read,
                records_created=created,
                records_updated=len(snapshot.games) - created,
                records_skipped=snapshot.records_read - len(snapshot.games),
            ),
        )

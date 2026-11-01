"""Set-based reconstruction of canonical season-ending team assignments."""

from psycopg2.extensions import connection as PgConnection
from app.database import open_database_cursor


class SeasonRangeError(ValueError):
    def __init__(self, *, first_season: int, last_season: int) -> None:
        super().__init__("first_season cannot be greater than last_season")
        self.first_season = first_season
        self.last_season = last_season


_CANDIDATES_SQL = r"""
WITH candidates AS (
    SELECT s.player_id, s.season_start_year, s.team_id,
           s.games_played, 0 AS source_priority
    FROM skater_season_stats s
    JOIN data_sources source ON source.id = s.source_id
    WHERE s.game_type = 2
      AND s.stat_scope = 'TEAM'
      AND s.team_id IS NOT NULL
      AND source.code = 'nhl'
      AND (%(first_season)s IS NULL OR s.season_start_year >= %(first_season)s)
      AND (%(last_season)s IS NULL OR s.season_start_year <= %(last_season)s)

    UNION ALL

    SELECT s.player_id, s.season_start_year, s.team_id,
           s.games_played, 0 AS source_priority
    FROM goalie_season_stats s
    JOIN data_sources source ON source.id = s.source_id
    WHERE s.game_type = 2
      AND s.stat_scope = 'TEAM'
      AND s.team_id IS NOT NULL
      AND source.code = 'nhl'
      AND (%(first_season)s IS NULL OR s.season_start_year >= %(first_season)s)
      AND (%(last_season)s IS NULL OR s.season_start_year <= %(last_season)s)

    UNION ALL

    SELECT s.player_id, s.season_start_year, s.team_id,
           s.games_played, 1 AS source_priority
    FROM skater_advanced_season_stats s
    JOIN data_sources source ON source.id = s.source_id
    WHERE s.situation = 'all'
      AND s.stat_scope = 'TEAM'
      AND s.team_id IS NOT NULL
      AND source.code = 'moneypuck'
      AND (%(first_season)s IS NULL OR s.season_start_year >= %(first_season)s)
      AND (%(last_season)s IS NULL OR s.season_start_year <= %(last_season)s)

    UNION ALL

    SELECT s.player_id, s.season_start_year, s.team_id,
           s.games_played, 1 AS source_priority
    FROM goalie_advanced_season_stats s
    JOIN data_sources source ON source.id = s.source_id
    WHERE s.situation = 'all'
      AND s.stat_scope = 'TEAM'
      AND s.team_id IS NOT NULL
      AND source.code = 'moneypuck'
      AND (%(first_season)s IS NULL OR s.season_start_year >= %(first_season)s)
      AND (%(last_season)s IS NULL OR s.season_start_year <= %(last_season)s)
),
canonical AS (
    SELECT DISTINCT ON (player_id, season_start_year)
           player_id, season_start_year, team_id
    FROM candidates
    ORDER BY player_id, season_start_year,
             source_priority,
             games_played DESC NULLS LAST,
             team_id
),
missing AS (
    SELECT canonical.*
    FROM canonical
    WHERE NOT EXISTS (
        SELECT 1
        FROM player_team_stints existing
        WHERE existing.player_id = canonical.player_id
          AND existing.season_start_year = canonical.season_start_year
    )
)
"""


_PLAN_SQL = (
    _CANDIDATES_SQL
    + r"""
SELECT
    (SELECT count(*) FROM canonical) AS canonical_assignments,
    (SELECT count(*) FROM missing) AS missing_assignments
"""
)


_APPLY_SQL = (
    _CANDIDATES_SQL
    + r"""
,
inserted AS (
    INSERT INTO player_team_stints
        (player_id, season_start_year, team_id)
    SELECT player_id, season_start_year, team_id
    FROM missing
    ORDER BY season_start_year, player_id
    ON CONFLICT DO NOTHING
    RETURNING id
)
SELECT
    (SELECT count(*) FROM canonical) AS canonical_assignments,
    (SELECT count(*) FROM missing) AS missing_assignments,
    (SELECT count(*) FROM inserted) AS inserted_assignments
"""
)


def build_team_stint_params(
    first_season: int | None, last_season: int | None
) -> dict[str, int | None]:
    if (
        first_season is not None
        and last_season is not None
        and first_season > last_season
    ):
        raise SeasonRangeError(first_season=first_season, last_season=last_season)
    return {"first_season": first_season, "last_season": last_season}


def plan_team_stint_backfill(
    connection: PgConnection,
    *,
    first_season: int | None = None,
    last_season: int | None = None,
) -> dict[str, int]:
    with open_database_cursor(connection) as cursor:
        cursor.execute(_PLAN_SQL, build_team_stint_params(first_season, last_season))
        canonical, missing = cursor.fetchone()
        return {
            "canonical_assignments": canonical,
            "missing_assignments": missing,
        }


def apply_team_stint_backfill(
    connection: PgConnection,
    *,
    first_season: int | None = None,
    last_season: int | None = None,
) -> dict[str, int]:
    with open_database_cursor(connection) as cursor:
        cursor.execute(_APPLY_SQL, build_team_stint_params(first_season, last_season))
        canonical, missing, inserted = cursor.fetchone()
        return {
            "canonical_assignments": canonical,
            "missing_assignments": missing,
            "inserted_assignments": inserted,
        }

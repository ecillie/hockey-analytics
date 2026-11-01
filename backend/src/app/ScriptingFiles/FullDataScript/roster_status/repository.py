"""PostgreSQL persistence adapter for roster-status synchronization."""

from datetime import date
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from app.database import open_database_cursor
from typing import Protocol, runtime_checkable
from psycopg2.extensions import connection as PgConnection

from app.ScriptingFiles.FullDataScript.roster_status.domain import (
    StoredRoster,
    RosterStatus,
    StoredPlayer,
)


@runtime_checkable
class RosterRepository(Protocol):
    def load_players(self) -> StoredRoster: ...

    def load_active_ltir_player_ids(self, as_of: date) -> frozenset[int]: ...

    def bulk_update_statuses(self, updates: Mapping[int, RosterStatus]) -> None: ...

    def save_ahl_external_ids(
        self,
        matches: Iterable[tuple[int, str, str]],
    ) -> None: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class PostgresRosterRepository:
    connection: PgConnection

    def load_players(self) -> StoredRoster:
        query = """
            SELECT
                p.id,
                p.first_name,
                p.last_name,
                p.birth_date,
                p.roster_status::text,
                MAX(pei.external_id) FILTER (WHERE ds.code = 'nhl') AS nhl_external_id,
                MAX(pei.external_id) FILTER (WHERE ds.code = 'ahl') AS ahl_external_id
            FROM players p
            LEFT JOIN player_external_ids pei ON pei.player_id = p.id
            LEFT JOIN data_sources ds ON ds.id = pei.source_id
            GROUP BY p.id, p.first_name, p.last_name, p.birth_date, p.roster_status
            ORDER BY p.id
        """
        with open_database_cursor(self.connection) as cursor:
            cursor.execute(query)
            return tuple(
                StoredPlayer(
                    id=row[0],
                    first_name=row[1],
                    last_name=row[2],
                    birth_date=row[3],
                    roster_status=RosterStatus[row[4]],
                    nhl_external_id=row[5],
                    ahl_external_id=row[6],
                )
                for row in cursor.fetchall()
            )

    def load_active_ltir_player_ids(self, as_of: date) -> frozenset[int]:
        query = """
            SELECT DISTINCT player_id
            FROM ltir_overrides
            WHERE start_date <= %s
              AND (end_date IS NULL OR end_date >= %s)
        """
        with open_database_cursor(self.connection) as cursor:
            cursor.execute(query, (as_of, as_of))
            return frozenset(row[0] for row in cursor.fetchall())

    def bulk_update_statuses(self, updates: Mapping[int, RosterStatus]) -> None:
        if len(updates) == 0:
            return
        query = """
            UPDATE players
            SET roster_status = %s::roster_status,
                roster_status_updated_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """
        with open_database_cursor(self.connection) as cursor:
            cursor.executemany(
                query,
                [
                    (status.database_value, player_id)
                    for player_id, status in updates.items()
                ],
            )

    def save_ahl_external_ids(
        self,
        matches: Iterable[tuple[int, str, str]],
    ) -> None:
        rows = list(matches)
        if len(rows) == 0:
            return
        source_query = """
            INSERT INTO data_sources (code, display_name, base_url)
            VALUES ('ahl', 'AHL', 'https://theahl.com')
            ON CONFLICT (code) DO NOTHING
        """
        query = """
            INSERT INTO player_external_ids (
                player_id,
                source_id,
                external_id,
                source_name
            )
            SELECT %s, ds.id, %s, %s
            FROM data_sources ds
            WHERE ds.code = 'ahl'
            ON CONFLICT (source_id, external_id) DO NOTHING
        """
        with open_database_cursor(self.connection) as cursor:
            cursor.execute(source_query)
            cursor.executemany(query, rows)

"""Source file adapters and typed PostgreSQL persistence helpers."""

from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
import json
from pathlib import Path

from psycopg2.extensions import connection as PgConnection, cursor as PgCursor
from psycopg2.extras import Json, execute_values

from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    Player,
    StatLayout,
    StatRow,
    Team,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.util import (
    split_name,
    parse_team_abbreviation,
    parse_csv,
)


type TransactionFactory = Callable[[], AbstractContextManager[PgConnection]]


def read_csv(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return parse_csv(handle.read(), source=str(path))


def load_source_ids(cursor: PgCursor) -> dict[str, int]:
    cursor.execute("SELECT code, id FROM data_sources")
    return {code: source_id for code, source_id in cursor.fetchall()}


def load_team_ids(cursor: PgCursor) -> dict[str, int]:
    cursor.execute("SELECT abbreviation, id FROM teams")
    return {abbr: team_id for abbr, team_id in cursor.fetchall()}


def ensure_seasons(cursor: PgCursor, years: Iterable[int]) -> None:
    rows = [
        (year, year + 1, f"{year}-{str(year + 1)[-2:]}") for year in sorted(set(years))
    ]
    if len(rows) > 0:
        execute_values(
            cursor,
            """INSERT INTO seasons (start_year,end_year,label) VALUES %s
               ON CONFLICT (start_year) DO NOTHING""",
            rows,
        )


def link_external_id(
    cursor: PgCursor,
    player_id: int,
    source_id: int,
    external_id: str,
    name: str,
    slug: str | None = None,
) -> None:
    cursor.execute(
        """INSERT INTO player_external_ids
               (player_id, source_id, external_id, source_slug, source_name)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (source_id, external_id) DO UPDATE SET
               source_slug = COALESCE(EXCLUDED.source_slug, player_external_ids.source_slug),
               source_name = EXCLUDED.source_name, updated_at = CURRENT_TIMESTAMP""",
        (player_id, source_id, external_id, slug, name),
    )


def ensure_teams(
    cursor: PgCursor,
    abbreviations: Iterable[object],
    details: Mapping[str, Team] | None = None,
) -> dict[str, int]:
    details = {} if details is None else details
    rows = []
    normalized = {
        abbreviation
        for item in abbreviations
        if (abbreviation := parse_team_abbreviation(item)) is not None
    }
    for abbreviation in sorted(normalized):
        team = details.get(abbreviation, Team(abbreviation=abbreviation))
        name = abbreviation if team.name is None or team.name == "" else team.name
        rows.append(
            (abbreviation, name, team.city, team.nhl_team_id, team.nhl_franchise_id)
        )
    if len(rows) > 0:
        execute_values(
            cursor,
            """INSERT INTO teams (abbreviation,name,city,nhl_team_id,nhl_franchise_id) VALUES %s
            ON CONFLICT (abbreviation) DO UPDATE SET
                name=CASE WHEN EXCLUDED.name=EXCLUDED.abbreviation THEN teams.name ELSE EXCLUDED.name END,
                city=COALESCE(EXCLUDED.city,teams.city),nhl_team_id=COALESCE(EXCLUDED.nhl_team_id,teams.nhl_team_id),
                nhl_franchise_id=COALESCE(EXCLUDED.nhl_franchise_id,teams.nhl_franchise_id),updated_at=CURRENT_TIMESTAMP""",
            rows,
        )
    return load_team_ids(cursor)


def upsert_player(cursor: PgCursor, source_id: int, player: Player) -> int:
    cursor.execute(
        "SELECT player_id FROM player_external_ids WHERE source_id=%s AND external_id=%s",
        (source_id, player.external_id),
    )
    found = cursor.fetchone()
    first_name, last_name = split_name(player.name)
    if found is not None:
        player_id = found[0]
        cursor.execute(
            """UPDATE players SET first_name=COALESCE(%s,first_name),last_name=COALESCE(%s,last_name),
            birth_date=COALESCE(%s,birth_date),primary_position=COALESCE(%s,primary_position),
            shoots_catches=COALESCE(%s,shoots_catches),nationality=COALESCE(%s,nationality),updated_at=CURRENT_TIMESTAMP WHERE id=%s""",
            (
                first_name if first_name != "" else None,
                last_name if last_name != "" else None,
                player.birth_date,
                player.position,
                player.shoots_catches,
                player.nationality,
                player_id,
            ),
        )
        return player_id
    cursor.execute(
        """INSERT INTO players (first_name,last_name,birth_date,primary_position,shoots_catches,nationality)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (
            first_name if first_name != "" else "Unknown",
            last_name if last_name != "" else "Unknown",
            player.birth_date,
            player.position,
            player.shoots_catches,
            player.nationality,
        ),
    )
    inserted = cursor.fetchone()
    assert inserted is not None
    player_id = inserted[0]
    cursor.execute(
        """INSERT INTO player_external_ids (player_id,source_id,external_id,source_slug,source_name)
        VALUES (%s,%s,%s,%s,%s)""",
        (player_id, source_id, player.external_id, player.source_slug, player.name),
    )
    return player_id


def resolve_nhl_player(
    cursor: PgCursor, nhl_id: int, moneypuck_id: int, row: StatRow
) -> int:
    cursor.execute(
        "SELECT player_id FROM player_external_ids WHERE source_id IN (%s,%s) AND external_id=%s ORDER BY source_id=%s DESC LIMIT 1",
        (nhl_id, moneypuck_id, row.external_id, nhl_id),
    )
    found = cursor.fetchone()
    player_id = (
        found[0]
        if found is not None
        else upsert_player(
            cursor,
            nhl_id,
            Player(
                external_id=row.external_id,
                name=row.name,
                position=row.position,
                shoots_catches=row.shoots_catches,
            ),
        )
    )
    link_external_id(cursor, player_id, nhl_id, row.external_id, row.name)
    return player_id


def write_stats(
    cursor: PgCursor,
    layout: StatLayout,
    source_id: int,
    values: tuple[tuple[object, ...], ...],
) -> tuple[int, int]:
    dimensions = (
        "player_id",
        "season_start_year",
        "team_id",
        "stat_scope",
        "situation" if layout.advanced else "game_type",
        "source_id",
    )
    metrics = tuple(spec.column for spec in layout.metrics)
    tail = (
        ("extra_metrics", "source_row_hash")
        if layout.advanced
        else ("source_row_hash",)
    )
    columns = ",".join(dimensions + metrics + tail)
    mutable = metrics + tail
    updates = ",".join(f"{column}=EXCLUDED.{column}" for column in mutable)
    grain = (
        "player_id,season_start_year,(COALESCE(team_id,0)),stat_scope,game_type,"
        + ("situation," if layout.advanced else "")
        + "source_id"
    )
    cursor.execute(
        f"SELECT count(*) FROM {layout.table} WHERE source_id=%s", (source_id,)
    )
    before = cursor.fetchone()
    assert before is not None
    if len(values) > 0:
        execute_values(
            cursor,
            f"INSERT INTO {layout.table} ({columns}) VALUES %s ON CONFLICT ({grain}) DO UPDATE SET {updates},updated_at=CURRENT_TIMESTAMP",
            values,
            page_size=1000,
        )
    cursor.execute(
        f"SELECT count(*) FROM {layout.table} WHERE source_id=%s", (source_id,)
    )
    after = cursor.fetchone()
    assert after is not None
    created = after[0] - before[0]
    return created, len(values) - created


def build_stat_values(
    row: StatRow,
    player_id: int,
    team_ids: Mapping[str, int],
    source_id: int,
    *,
    advanced: bool,
) -> tuple[object, ...]:
    team_id = team_ids.get(row.teams[0]) if len(row.teams) == 1 else None
    scope = "TEAM" if team_id is not None else "TOTAL"
    dimension = row.situation if advanced else row.game_type
    extra = (
        (Json(json.loads(row.extra_metrics_json)), row.source_row_hash)
        if advanced and row.extra_metrics_json is not None
        else (row.source_row_hash,)
    )
    return (
        player_id,
        row.season,
        team_id,
        scope,
        dimension,
        source_id,
        *row.metrics,
        *extra,
    )

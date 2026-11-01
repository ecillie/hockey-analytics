"""Typed PostgreSQL adapter for the active CapWages snapshot."""

from collections import defaultdict
from collections.abc import Callable, Generator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.database import open_database_transaction
from app.ScriptingFiles.FullDataScript.contracts.domain import (
    ActiveContractSnapshot,
    ActivePlayer,
    ContractSeason,
    ParsedContract,
)
from app.ScriptingFiles.FullDataScript.contracts.errors import ActiveSeasonCapError
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import Player
from app.ScriptingFiles.FullDataScript.source_ingestion.repository import (
    ensure_seasons as _ensure_seasons,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.repository import (
    ensure_teams as _ensure_teams,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.repository import (
    link_external_id as _link_external_id,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.repository import (
    load_source_ids as _source_ids,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.repository import (
    upsert_player,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.util import (
    normalize_nationality as _nationality,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.util import (
    normalize_position as _position,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.util import (
    split_name as _split_name,
)
from psycopg2.extensions import cursor as PgCursor
from psycopg2.extras import Json


def upsert_active_season(
    cursor: PgCursor,
    *,
    contract_id: int,
    external_id: str,
    owning_team_id: int | None,
    detail: ContractSeason,
) -> int:
    year = detail.season_start_year
    cap_hit = detail.cap_hit_cents
    cursor.execute(
        "SELECT salary_cap_cents FROM seasons WHERE start_year=%s",
        (year,),
    )
    cap_row = cursor.fetchone()
    cap_pct = (
        Decimal(cap_hit) / cap_row[0]
        if cap_row is not None and cap_row[0] not in (None, 0)
        else None
    )
    if cap_pct is not None and cap_pct > 1:
        raise ActiveSeasonCapError(external_id=external_id, season=year)
    cursor.execute(
        """SELECT 1 FROM contract_seasons
           WHERE contract_id=%s AND season_start_year=%s""",
        (contract_id, year),
    )
    season_existed = cursor.fetchone() is not None
    cursor.execute(
        """INSERT INTO contract_seasons (contract_id,season_start_year,owning_team_id,cap_hit_cents,cap_percentage,is_slide)
           VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (contract_id,season_start_year) DO UPDATE SET
           owning_team_id=EXCLUDED.owning_team_id,cap_hit_cents=EXCLUDED.cap_hit_cents,
           cap_percentage=EXCLUDED.cap_percentage,
           is_slide=EXCLUDED.is_slide,updated_at=CURRENT_TIMESTAMP""",
        (
            contract_id,
            year,
            owning_team_id,
            cap_hit,
            cap_pct,
            detail.is_slide,
        ),
    )
    return int(not season_existed)


def upsert_active_contract(
    cursor: PgCursor,
    *,
    player_id: int,
    source_id: int,
    item: ActivePlayer,
    contract: ParsedContract,
    index: int,
    team_ids: Mapping[str, int],
) -> tuple[int, int]:
    details = contract.seasons
    years = [season.season_start_year for season in details]
    start, end = min(years), max(years)
    external_id = f"{item.slug}:{start}:{end}:{index}"
    cursor.execute(
        "SELECT 1 FROM contracts WHERE source_id=%s AND external_id=%s",
        (source_id, external_id),
    )
    contract_existed = cursor.fetchone() is not None
    total_cents = contract.total_value_cents
    average_cents = details[0].cap_hit_cents
    expiry = contract.expiry_status
    contract_type = contract.contract_type
    cursor.execute(
        """INSERT INTO contracts (player_id,signing_team_id,source_id,external_id,start_season,end_season,
               term_years,contract_type,expiry_status,total_value_cents,average_value_cents,is_entry_level,source_payload)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (source_id,external_id) WHERE source_id IS NOT NULL AND external_id IS NOT NULL
           DO UPDATE SET player_id=EXCLUDED.player_id,signing_team_id=EXCLUDED.signing_team_id,
               start_season=EXCLUDED.start_season,end_season=EXCLUDED.end_season,
               term_years=EXCLUDED.term_years,contract_type=EXCLUDED.contract_type,
               expiry_status=EXCLUDED.expiry_status,total_value_cents=EXCLUDED.total_value_cents,
               average_value_cents=EXCLUDED.average_value_cents,is_entry_level=EXCLUDED.is_entry_level,
               source_payload=EXCLUDED.source_payload,updated_at=CURRENT_TIMESTAMP RETURNING id""",
        (
            player_id,
            team_ids.get(
                str(
                    contract.signing_team
                    if contract.signing_team is not None
                    else item.team
                ).upper()
            ),
            source_id,
            external_id,
            start,
            end,
            len(years),
            contract_type,
            expiry,
            total_cents,
            average_cents,
            "ENTRY" in (contract_type if contract_type is not None else "").upper()
            or "ELC" in (contract_type if contract_type is not None else "").upper(),
            Json(contract.source_payload),
        ),
    )
    contract_id = cursor.fetchone()[0]
    seasons_created = sum(
        upsert_active_season(
            cursor,
            contract_id=contract_id,
            external_id=external_id,
            owning_team_id=team_ids.get(item.team),
            detail=detail,
        )
        for detail in details
    )
    return int(not contract_existed), seasons_created


def resolve_active_player(
    cursor: PgCursor,
    item: ActivePlayer,
    capwages_id: int,
    by_name: dict[tuple[str, str], list[int]],
) -> int:
    first, last = _split_name(item.name)
    matches = by_name.get((first.lower(), last.lower()), [])
    if len(matches) == 1:
        player_id = matches[0]
        _link_external_id(
            cursor,
            player_id,
            capwages_id,
            item.slug,
            item.name,
            item.slug,
        )
        return player_id
    player_id = upsert_player(
        cursor,
        capwages_id,
        Player(
            external_id=item.slug,
            name=item.name,
            source_slug=item.slug,
            birth_date=item.birth_date,
            position=_position(item.position),
            nationality=_nationality(item.nationality),
        ),
    )
    by_name[(first.lower(), last.lower())].append(player_id)
    return player_id


def save_active_snapshot(
    cursor: PgCursor, snapshot: ActiveContractSnapshot
) -> dict[str, int | str]:
    players = tuple(profile.player for profile in snapshot.profiles)
    contracts_by_slug = {
        profile.player.slug: profile.contracts for profile in snapshot.profiles
    }
    sources = _source_ids(cursor)
    capwages_id = sources["capwages"]
    contract_teams = [
        contract.signing_team
        for contracts in contracts_by_slug.values()
        for contract in contracts
    ]
    team_ids = _ensure_teams(cursor, [item.team for item in players] + contract_teams)
    contract_years = [
        season.season_start_year
        for contracts in contracts_by_slug.values()
        for contract in contracts
        for season in contract.seasons
    ]
    _ensure_seasons(cursor, contract_years)
    cursor.execute(
        """SELECT p.id, lower(p.first_name), lower(p.last_name) FROM players p"""
    )
    by_name = defaultdict(list)
    for player_id, first, last in cursor.fetchall():
        by_name[(first, last)].append(player_id)
    contract_count = season_count = contract_created_count = season_created_count = 0
    for item in players:
        player_id = resolve_active_player(cursor, item, capwages_id, by_name)
        for index, contract in enumerate(contracts_by_slug[item.slug]):
            created, seasons_created = upsert_active_contract(
                cursor,
                player_id=player_id,
                source_id=capwages_id,
                item=item,
                contract=contract,
                index=index,
                team_ids=team_ids,
            )
            contract_count += 1
            season_count += len(contract.seasons)
            contract_created_count += created
            season_created_count += seasons_created
    records_created = contract_created_count + season_created_count
    return {
        "players": len(players),
        "contracts": contract_count,
        "contract_seasons": season_count,
        "profile_failures": len(snapshot.failed_slugs),
        "records_read": len(players) + contract_count + season_count,
        "records_created": records_created,
        "records_updated": contract_count + season_count - records_created,
        "records_skipped": len(snapshot.failed_slugs),
        "reconciliation_policy": "retain_missing",
    }


@runtime_checkable
class ActiveContractRepository(Protocol):
    def save_snapshot(
        self, snapshot: ActiveContractSnapshot
    ) -> dict[str, int | str]: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class PostgresActiveContractRepository:
    cursor: PgCursor

    def save_snapshot(self, snapshot: ActiveContractSnapshot) -> dict[str, int | str]:
        return save_active_snapshot(self.cursor, snapshot)


type ActiveRepositoryFactory = Callable[
    [], AbstractContextManager[ActiveContractRepository]
]


@contextmanager
def open_active_repository() -> Generator[ActiveContractRepository]:
    with open_database_transaction() as connection, connection.cursor() as cursor:
        yield PostgresActiveContractRepository(cursor=cursor)

"""Schema-native ingestion for the TradeValue data sources.

The older scripts in this directory target a retired ORM schema.  This module
loads the same sources directly into ``backend/database/schema.sql`` and keeps
each source stage transactional and repeatable.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from contextlib import AbstractContextManager
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import logging
from pathlib import Path
import re
from typing import Any, Iterable

from psycopg2.extras import Json
import requests

from app.database import database_transaction, init_db
from app.ScriptingFiles.FullDataScript.ingestion_tracking import tracked_ingestion
from contextlib import nullcontext
from app.ScriptingFiles.FullDataScript import capspace
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    DataQualityReport as DataQualityReport,
    Player,
    PlayerKind,
    serialize_summary,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.errors import (
    IngestionValidationError as IngestionValidationError,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.http import (
    SourceSession,
    SourceClient,
    SynchronizedSourceClient,
    SessionSourceClient,
    http_session as http_session,
    open_source_client,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.policy import (
    QualityPolicy,
    RowPolicy,
    validate_rows,
    stat_violation,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.repository import (
    source_ids as _source_ids,
    ensure_teams as _ensure_teams,
    ensure_seasons as _ensure_seasons,
    link_external_id as _link_external_id,
    upsert_player,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.util import (
    normalize_position as _position,
    normalize_nationality as _nationality,
    split_name as _split_name,
    slug_from_name as _slug_from_name,
    season_start_year as _season_start_year,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.domain import (
    MoneyPuckOptions,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.services import (
    MoneyPuckService,
    MoneyPuckRepository,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.repository import (
    PostgresMoneyPuckRepository,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.domain import (
    NhlStatsOptions,
    NhlRosterOptions,
    StatsJob,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.services import (
    NhlStatsService,
    NhlRosterService,
    NhlStatsRepository,
    NhlRosterRepository,
    SourceClientFactory,
    fetch_stats_pages,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.repository import (
    PostgresNhlStatsRepository,
    PostgresNhlRosterRepository,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.schedule.domain import (
    ScheduleOptions,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.schedule.services import (
    ScheduleService,
    ScheduleRepository,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.schedule.repository import (
    PostgresScheduleRepository,
)


LOGGER = logging.getLogger(__name__)
RECONCILIATION_POLICY = "retain_missing"


def _money_cents(value: Any) -> int | None:
    if value in (None, ""):
        return None
    cleaned = re.sub(r"[^0-9.-]", "", str(value))
    if not cleaned:
        return None
    try:
        return int((Decimal(cleaned) * 100).quantize(Decimal("1")))
    except InvalidOperation:
        return None


def _capwages_birth_date(value: Any) -> str | None:
    match = re.fullmatch(r"(\d{2})-(\d{1,2})-(\d{1,2})", str(value or ""))
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    year += 1900 if year >= 30 else 2000
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _capwages_active(
    session: requests.Session, *, minimum_rows: int = 500
) -> list[list[Any]]:
    response = session.get("https://capwages.com/players/active", timeout=60)
    response.raise_for_status()
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        response.text,
        re.DOTALL,
    )
    if not match:
        raise RuntimeError(
            "CapWages active-player page no longer contains __NEXT_DATA__"
        )
    players = (
        json.loads(match.group(1))
        .get("props", {})
        .get("pageProps", {})
        .get("playersArray", [])
    )
    if len(players) < minimum_rows:
        raise RuntimeError(
            f"CapWages returned an unexpectedly partial active-player list ({len(players)} rows)"
        )
    return players


def _capwages_contracts(session: requests.Session, slug: str) -> list[dict]:
    response = session.get(f"https://capwages.com/players/{slug}", timeout=30)
    response.raise_for_status()
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        response.text,
        re.DOTALL,
    )
    if not match:
        return []
    return (
        json.loads(match.group(1))
        .get("props", {})
        .get("pageProps", {})
        .get("player", {})
        .get("contracts", [])
    )


def _parse_capwages_players(
    rows: Iterable[list[Any]], *, minimum_rows: int = 500
) -> list[dict[str, Any]]:
    players = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 4 or not str(row[0] or "").strip():
            continue
        slug = row[1] or _slug_from_name(row[0])
        if not slug:
            continue
        players.append(
            {
                "name": row[0],
                "slug": slug,
                "team": row[2],
                "position": row[3],
                "nationality": row[7] if len(row) > 7 else None,
                "birth_date": _capwages_birth_date(row[30] if len(row) > 30 else None),
            }
        )
    if len(players) < minimum_rows:
        raise IngestionValidationError(
            f"Only {len(players)} CapWages player rows could be assigned profile slugs; "
            f"minimum is {minimum_rows}"
        )
    return players


@tracked_ingestion("capwages")
def ingest_capwages(
    session: requests.Session,
    *,
    minimum_players: int = 500,
    minimum_profile_success_ratio: float = 0.98,
) -> dict[str, int | str]:
    active = _capwages_active(session, minimum_rows=minimum_players)
    players = _parse_capwages_players(active, minimum_rows=minimum_players)
    contracts_by_slug = {}
    profile_failures = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(_capwages_contracts, session, item["slug"]): item["slug"]
            for item in players
        }
        for future in as_completed(futures):
            slug = futures[future]
            try:
                contracts_by_slug[slug] = future.result()
            except requests.RequestException as exc:
                LOGGER.warning("CapWages profile unavailable for %s: %s", slug, exc)
                profile_failures.append(slug)
    success_ratio = (len(players) - len(profile_failures)) / len(players)
    if success_ratio < minimum_profile_success_ratio:
        raise IngestionValidationError(
            f"CapWages profile success ratio {success_ratio:.2%} is below "
            f"{minimum_profile_success_ratio:.2%}; refusing partial refresh"
        )

    with database_transaction() as connection:
        cursor = connection.cursor()
        sources = _source_ids(cursor)
        capwages_id = sources["capwages"]
        contract_teams = [
            contract.get("signingTeam")
            for contracts in contracts_by_slug.values()
            for contract in contracts
        ]
        team_ids = _ensure_teams(
            cursor, [item["team"] for item in players] + contract_teams
        )
        contract_years = []
        for contracts in contracts_by_slug.values():
            for contract in contracts:
                for detail in contract.get("details") or []:
                    match = re.match(r"(\d{4})", str(detail.get("season") or ""))
                    if match:
                        contract_years.append(int(match.group(1)))
        _ensure_seasons(cursor, contract_years)
        cursor.execute(
            """SELECT p.id, lower(p.first_name), lower(p.last_name) FROM players p"""
        )
        by_name = defaultdict(list)
        for player_id, first, last in cursor.fetchall():
            by_name[(first, last)].append(player_id)
        contract_count = season_count = 0
        contract_created_count = season_created_count = 0
        for item in players:
            first, last = _split_name(item["name"])
            matches = by_name.get((first.lower(), last.lower()), [])
            if len(matches) == 1:
                player_id = matches[0]
                _link_external_id(
                    cursor,
                    player_id,
                    capwages_id,
                    item["slug"],
                    item["name"],
                    item["slug"],
                )
            else:
                player_id = upsert_player(
                    cursor,
                    capwages_id,
                    Player(
                        external_id=item["slug"],
                        name=item["name"],
                        source_slug=item["slug"],
                        birth_date=item["birth_date"],
                        position=_position(item["position"]),
                        nationality=_nationality(item["nationality"]),
                    ),
                )
                by_name[(first.lower(), last.lower())].append(player_id)
            for index, contract in enumerate(contracts_by_slug.get(item["slug"], [])):
                details = contract.get("details") or []
                if not details:
                    continue
                years = []
                for detail in details:
                    match = re.match(r"(\d{4})", str(detail.get("season") or ""))
                    if match:
                        years.append(int(match.group(1)))
                if not years:
                    continue
                unique_years = sorted(set(years))
                if len(unique_years) != len(years) or unique_years != list(
                    range(unique_years[0], unique_years[-1] + 1)
                ):
                    raise IngestionValidationError(
                        f"CapWages contract {item['slug']} has duplicate or non-contiguous seasons"
                    )
                start, end = min(years), max(years)
                external_id = f"{item['slug']}:{start}:{end}:{index}"
                cursor.execute(
                    "SELECT 1 FROM contracts WHERE source_id=%s AND external_id=%s",
                    (capwages_id, external_id),
                )
                contract_existed = cursor.fetchone() is not None
                total_cents = _money_cents(contract.get("value"))
                average_cents = _money_cents(details[0].get("capHit"))
                expiry = str(contract.get("expiryStatus") or "").upper()
                expiry = (
                    "RFA" if "RFA" in expiry else "UFA" if "UFA" in expiry else None
                )
                contract_type = str(contract.get("type") or "")[:32] or None
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
                            str(contract.get("signingTeam") or item["team"]).upper()
                        ),
                        capwages_id,
                        external_id,
                        start,
                        end,
                        len(years),
                        contract_type,
                        expiry,
                        total_cents,
                        average_cents,
                        "ENTRY" in (contract_type or "").upper()
                        or "ELC" in (contract_type or "").upper(),
                        Json(contract),
                    ),
                )
                contract_id = cursor.fetchone()[0]
                contract_count += 1
                contract_created_count += int(not contract_existed)
                for detail in details:
                    match = re.match(r"(\d{4})", str(detail.get("season") or ""))
                    if not match:
                        continue
                    year = int(match.group(1))
                    cap_hit = _money_cents(detail.get("capHit"))
                    if cap_hit is None or cap_hit < 0:
                        raise IngestionValidationError(
                            f"CapWages contract {external_id} has an invalid cap hit"
                        )
                    cursor.execute(
                        "SELECT salary_cap_cents FROM seasons WHERE start_year=%s",
                        (year,),
                    )
                    cap_row = cursor.fetchone()
                    cap_pct = (
                        Decimal(cap_hit) / cap_row[0]
                        if cap_row and cap_row[0]
                        else None
                    )
                    if cap_pct is not None and cap_pct > 1:
                        raise IngestionValidationError(
                            f"CapWages contract {external_id} exceeds the season salary cap"
                        )
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
                            team_ids.get(item["team"]),
                            cap_hit,
                            cap_pct,
                            "slide" in str(detail.get("type") or "").lower(),
                        ),
                    )
                    season_count += 1
                    season_created_count += int(not season_existed)
        cursor.close()
    LOGGER.info(
        "CapWages loaded: active_players=%s contracts=%s contract_seasons=%s",
        len(players),
        contract_count,
        season_count,
    )
    records_created = contract_created_count + season_created_count
    return {
        "players": len(players),
        "contracts": contract_count,
        "contract_seasons": season_count,
        "profile_failures": len(profile_failures),
        "records_read": len(players) + contract_count + season_count,
        "records_created": records_created,
        "records_updated": contract_count + season_count - records_created,
        "records_skipped": len(profile_failures),
        "reconciliation_policy": RECONCILIATION_POLICY,
    }


def existing_capwages_summary() -> dict[str, int]:
    """Return the durable last-good CapWages snapshot already in PostgreSQL."""
    with database_transaction() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """SELECT
                   (SELECT count(DISTINCT external.player_id)
                      FROM player_external_ids external WHERE external.source_id = source.id),
                   (SELECT count(*) FROM contracts WHERE contracts.source_id = source.id),
                   (SELECT count(*) FROM contract_seasons
                      JOIN contracts ON contracts.id = contract_seasons.contract_id
                     WHERE contracts.source_id = source.id)
               FROM data_sources source WHERE source.code = 'capwages'"""
        )
        players, contracts, contract_seasons = cursor.fetchone()
        cursor.close()
    if not contracts:
        raise RuntimeError(
            "CapWages is unavailable and no last-good database snapshot exists"
        )
    return {
        "players": players,
        "contracts": contracts,
        "contract_seasons": contract_seasons,
        "cached": 1,
    }


def validate_and_deduplicate_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    source: str,
    required_fields: Iterable[str],
    grain_fields: Iterable[str],
    season_field: str = "season",
    expected_seasons: Iterable[int] | None = None,
    integer_fields: Iterable[str] = (),
    numeric_fields: Iterable[str] = (),
) -> tuple[list[dict[str, object]], DataQualityReport]:
    valid, report = validate_rows(
        rows,
        RowPolicy(
            source=source,
            required_fields=tuple(required_fields),
            grain_fields=tuple(grain_fields),
            season_field=season_field,
            expected_seasons=()
            if expected_seasons is None
            else tuple(expected_seasons),
            integer_fields=frozenset(integer_fields),
            numeric_fields=frozenset(numeric_fields),
        ),
    )
    return list(valid), report


def enforce_quality_thresholds(
    report: DataQualityReport, *, minimum_rows: int, maximum_duplicate_ratio: float
) -> None:
    if violation := QualityPolicy(
        minimum_rows=minimum_rows, maximum_duplicate_ratio=maximum_duplicate_ratio
    ).find_violation(report):
        raise violation


def validate_stat_invariants(
    kind: str, row: Mapping[str, object], *, source: str
) -> None:
    if violation := stat_violation(kind, row, source=source):
        raise violation


def default_moneypuck_options(
    *,
    expected_seasons: Iterable[int] = range(2008, 2026),
    minimum_rows_per_kind: int = 100,
    maximum_duplicate_ratio: float = 0.01,
) -> MoneyPuckOptions:
    data_dir = Path(
        os.environ.get(
            "TRADEVALUE_DATA_DIR", Path(__file__).resolve().parents[4].joinpath("data")
        )
    )
    return MoneyPuckOptions(
        skater_file=data_dir.joinpath("skater advanced", "skaters_2008_to_2024.csv"),
        goalie_file=data_dir.joinpath("goalie_advanced", "goalies_2008_to_2024.csv"),
        expected_seasons=tuple(expected_seasons),
        minimum_rows_per_kind=minimum_rows_per_kind,
        maximum_duplicate_ratio=maximum_duplicate_ratio,
    )


@tracked_ingestion("moneypuck")
def ingest_moneypuck(
    session: SourceSession,
    *,
    expected_seasons: Iterable[int] = range(2008, 2026),
    minimum_rows_per_kind: int = 100,
    maximum_duplicate_ratio: float = 0.01,
    options: MoneyPuckOptions | None = None,
    repository: MoneyPuckRepository | None = None,
) -> dict[str, int | str]:
    options = (
        default_moneypuck_options(
            expected_seasons=expected_seasons,
            minimum_rows_per_kind=minimum_rows_per_kind,
            maximum_duplicate_ratio=maximum_duplicate_ratio,
        )
        if options is None
        else options
    )
    repository = (
        PostgresMoneyPuckRepository(transaction=database_transaction)
        if repository is None
        else repository
    )
    return serialize_summary(
        MoneyPuckService(
            client=SessionSourceClient(session=session),
            repository=repository,
            options=options,
        ).ingest()
    )


@tracked_ingestion("nhl")
def ingest_nhl_rosters(
    session: SourceSession,
    *,
    minimum_teams: int = 30,
    minimum_active_players: int = 500,
    season_start_year: int | None = None,
    repository: NhlRosterRepository | None = None,
) -> dict[str, int | str]:
    repository = (
        PostgresNhlRosterRepository(transaction=database_transaction)
        if repository is None
        else repository
    )
    options = NhlRosterOptions(
        season=_season_start_year() if season_start_year is None else season_start_year,
        minimum_teams=minimum_teams,
        minimum_active_players=minimum_active_players,
    )
    return serialize_summary(
        NhlRosterService(
            client=SessionSourceClient(session=session),
            repository=repository,
            options=options,
        ).ingest()
    )


def _nhl_stats_pages(
    session: SourceSession, endpoint: str, season: int, game_type: int
) -> list[dict[str, object]]:
    return list(
        fetch_stats_pages(
            SessionSourceClient(session=session),
            StatsJob(kind=PlayerKind(endpoint), season=season, game_type=game_type),
        )
    )


@tracked_ingestion("nhl")
def ingest_nhl_stats(
    session: SourceSession | None = None,
    first_season: int = 2008,
    last_season: int = 2025,
    *,
    client_factory: SourceClientFactory | None = None,
    repository: NhlStatsRepository | None = None,
    options: NhlStatsOptions | None = None,
) -> dict[str, int | str]:
    options = (
        NhlStatsOptions(first_season=first_season, last_season=last_season)
        if options is None
        else options
    )
    repository = (
        PostgresNhlStatsRepository(transaction=database_transaction)
        if repository is None
        else repository
    )
    if client_factory is None:
        client_factory = (
            open_source_client
            if session is None
            else BorrowedSourceClientFactory(
                client=SynchronizedSourceClient(
                    client=SessionSourceClient(session=session)
                )
            )
        )
    return serialize_summary(
        NhlStatsService(
            client_factory=client_factory, repository=repository, options=options
        ).ingest()
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class BorrowedSourceClientFactory:
    client: SourceClient

    def __call__(self) -> AbstractContextManager[SourceClient]:
        return nullcontext(self.client)


@tracked_ingestion("nhl")
def ingest_schedule(
    session: SourceSession,
    season: int = 2026,
    *,
    minimum_games: int = 100,
    repository: ScheduleRepository | None = None,
) -> dict[str, int | str]:
    repository = (
        PostgresScheduleRepository(transaction=database_transaction)
        if repository is None
        else repository
    )
    return serialize_summary(
        ScheduleService(
            client=SessionSourceClient(session=session),
            repository=repository,
            options=ScheduleOptions(season=season, minimum_games=minimum_games),
        ).ingest()
    )


def run_all() -> dict[str, Mapping[str, object]]:
    init_db()
    session = http_session()
    try:
        results: dict[str, Mapping[str, object]] = {}
        results["moneypuck"] = ingest_moneypuck(session)
        results["nhl_rosters"] = ingest_nhl_rosters(session)
        results["nhl_stats"] = ingest_nhl_stats()
        try:
            results["capwages"] = ingest_capwages(session)
        except (
            requests.RequestException,
            RuntimeError,
            IngestionValidationError,
        ) as exc:
            results["capwages"] = existing_capwages_summary()
            LOGGER.warning(
                "CapWages refresh unavailable; retained last-good database snapshot: %s",
                exc,
            )
        try:
            results["historical_contracts"] = capspace.ingest_historical_contracts(
                session
            )
        except (
            requests.RequestException,
            RuntimeError,
            IngestionValidationError,
        ) as exc:
            results["historical_contracts"] = (
                capspace.existing_historical_contract_summary()
            )
            LOGGER.warning(
                "Historical contract refresh unavailable; retained last-good snapshot: %s",
                exc,
            )
        results["schedule"] = ingest_schedule(session)
        return results
    finally:
        session.close()

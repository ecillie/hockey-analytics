"""Gap-driven historical NHL contract ingestion from CapSpace and CapWages.

The normal CapWages refresh starts from its active-player index. This module
fills the resulting historical gaps by selecting players from NHL stats and
querying CapSpace directly by NHL ID, then trying identity-validated CapWages
profiles when CapSpace cannot cover a requested season. Parsing and money
normalisation are deliberately independent of PostgreSQL so saved source pages
can be regression-tested without network access.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from decimal import Decimal
import argparse
import hashlib
import json
import time
from typing import Any, Iterable, Protocol, runtime_checkable
from collections.abc import Mapping
from urllib.parse import urlsplit

import requests
from psycopg2.extras import Json, execute_values

from app.ScriptingFiles.FullDataScript.contracts.schemas import (
    parse_source_document,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.contracts import (
    parse_contract_document as _parse_contract_document,
    parse_capspace_page as parse_capspace_page,
    normalize_contracts as normalize_contracts,
)
from app.ScriptingFiles.FullDataScript.contracts.domain import (
    Candidate as Candidate,
    ContractSeason as ContractSeason,
    ParsedContract as ParsedContract,
    ProfileResult as ProfileResult,
    ProfileSource,
    ProfileStatus,
    AbsenceReason,
    FailureReason,
    ContractsAbsent,
    ProfileFailure,
    parsed_profile,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.serialization import (
    serialize_contract,
)
from app.ScriptingFiles.FullDataScript.contracts.errors import (
    CapSpaceError as CapSpaceError,
    CapSpaceParseError as CapSpaceParseError,
    MissingContractError,
)
from app.ScriptingFiles.FullDataScript.contracts.util import (
    money_to_cents as money_to_cents,
    season_start_year as season_start_year,
    clean_text as _clean_text,
)
from app.ScriptingFiles.FullDataScript.contracts.policy import (
    capwages_document_matches as _capwages_document_matches,
)
from app.database import database_transaction, init_db
from app.ScriptingFiles.FullDataScript.source_ingestion.util import (
    slug_from_name as _slug_from_name,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.http import http_session
from app.ScriptingFiles.FullDataScript.ingestion_tracking import tracked_ingestion


@runtime_checkable
class ProfileResponse(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def text(self) -> str: ...

    @property
    def headers(self) -> Mapping[str, str]: ...


@runtime_checkable
class ProfileSession(Protocol):
    def get(self, url: str, *, timeout: float) -> ProfileResponse: ...


CAPSPACE_BASE_URL = "https://cap-space.com"
CAPWAGES_BASE_URL = "https://capwages.com"
CAPSPACE_SOURCE = ProfileSource.CAPSPACE
CAPWAGES_SOURCE = ProfileSource.CAPWAGES
STATUS_FAILED = ProfileStatus.FAILED
STATUS_NO_CONTRACTS = ProfileStatus.NO_CONTRACTS
STATUS_NO_MATCHING_CONTRACTS = ProfileStatus.NO_MATCHING_CONTRACTS
STATUS_NO_NHL_ID = ProfileStatus.NO_NHL_ID
STATUS_NOT_FOUND = ProfileStatus.NOT_FOUND
STATUS_PARSE_FAILED = ProfileStatus.PARSE_FAILED
STATUS_SUCCEEDED = ProfileStatus.SUCCEEDED
FAILURE_STATUSES = frozenset({STATUS_FAILED, STATUS_PARSE_FAILED})
RETRYABLE_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})
CAPWAGES_SLUG_SUFFIXES = ("", "-1", "-2", "-3")
DEFAULT_FIRST_SEASON = 2008
DEFAULT_LAST_SEASON = 2025
MAX_WORKERS = 8
DEFAULT_BATCH_SIZE = 100
MAX_BATCH_SIZE = 1000
STAT_SEASONS_CTE = """stat_seasons AS (
    SELECT DISTINCT player_id,season_start_year
      FROM skater_season_stats
     WHERE game_type=2
       AND COALESCE(games_played,0)>0
       AND season_start_year BETWEEN %s AND %s
    UNION
    SELECT DISTINCT player_id,season_start_year
      FROM goalie_season_stats
     WHERE game_type=2
       AND COALESCE(games_played,0)>0
       AND season_start_year BETWEEN %s AND %s
)"""
MISSING_CONTRACT_PREDICATE = """NOT EXISTS (
    SELECT 1
      FROM contracts c
      JOIN contract_seasons cs ON cs.contract_id=c.id
     WHERE c.player_id=s.player_id
       AND cs.season_start_year=s.season_start_year
)"""


def select_candidates(
    cursor,
    *,
    first_season: int = DEFAULT_FIRST_SEASON,
    last_season: int = DEFAULT_LAST_SEASON,
    player_id: int | None = None,
    nhl_id: str | None = None,
    limit: int | None = None,
    force: bool = False,
) -> list[Candidate]:
    filters = []
    params: list[Any] = [
        first_season,
        last_season,
        first_season,
        last_season,
    ]
    if player_id is not None:
        filters.append("p.id = %s")
        params.append(player_id)
    if nhl_id is not None:
        filters.append("nhl.external_id = %s")
        params.append(str(nhl_id))
    if not force:
        filters.append(MISSING_CONTRACT_PREDICATE)
    where_clause = " AND ".join(filters) if filters else "TRUE"
    limit_sql = " LIMIT %s" if limit else ""
    if limit:
        params.append(limit)
    cursor.execute(
        f"""WITH {STAT_SEASONS_CTE}
             SELECT s.player_id, p.first_name, p.last_name, nhl.external_id,
                    array_agg(s.season_start_year ORDER BY s.season_start_year)
               FROM stat_seasons s
               JOIN players p ON p.id=s.player_id
               LEFT JOIN data_sources nhl_src ON nhl_src.code='nhl'
               LEFT JOIN player_external_ids nhl
                 ON nhl.player_id=p.id AND nhl.source_id=nhl_src.id
              WHERE {where_clause}
              GROUP BY s.player_id,p.first_name,p.last_name,nhl.external_id
              ORDER BY s.player_id{limit_sql}""",
        params,
    )
    return [
        Candidate(
            player_id=int(row[0]),
            first_name=row[1],
            last_name=row[2],
            nhl_id=str(row[3]) if row[3] else None,
            missing_seasons=tuple(row[4]),
        )
        for row in cursor.fetchall()
    ]


def _team_lookup(cursor) -> dict[str, int]:
    cursor.execute("SELECT id,abbreviation,name FROM teams")
    lookup: dict[str, int] = {}
    for team_id, abbreviation, name in cursor.fetchall():
        for value in (abbreviation, name):
            key = _clean_text(value).casefold()
            if key:
                lookup[key] = int(team_id)
    return lookup


@dataclass(frozen=True)
class _PersistenceContext:
    season_caps: dict[int, int | None]
    team_lookup: dict[str, int]


def _load_persistence_context(
    cursor,
    first_season: int,
    last_season: int,
) -> _PersistenceContext:
    cursor.execute(
        """SELECT start_year,salary_cap_cents
             FROM seasons
            WHERE start_year BETWEEN %s AND %s""",
        (first_season - 10, last_season),
    )
    return _PersistenceContext(
        season_caps={int(year): cap for year, cap in cursor.fetchall()},
        team_lookup=_team_lookup(cursor),
    )


def _player_stint_teams(cursor, player_id: int) -> dict[int, tuple[int, ...]]:
    cursor.execute(
        """SELECT DISTINCT season_start_year,team_id
             FROM player_team_stints
            WHERE player_id=%s""",
        (player_id,),
    )
    teams_by_season: dict[int, list[int]] = {}
    for season, team_id in cursor.fetchall():
        teams_by_season.setdefault(int(season), []).append(int(team_id))
    return {season: tuple(team_ids) for season, team_ids in teams_by_season.items()}


def _resolve_team_id(
    team_lookup: dict[str, int],
    stint_teams: dict[int, tuple[int, ...]],
    season: int,
    explicit: str | None,
) -> int | None:
    explicit_id = team_lookup.get(_clean_text(explicit).casefold())
    if explicit_id is not None:
        return explicit_id
    teams = stint_teams.get(season, ())
    return teams[0] if len(teams) == 1 else None


def _compatible(
    existing: tuple[Any, ...], incoming: ParsedContract, team_id: int | None
) -> bool:
    _, existing_team, _, _, _, _, _, _, total_value, _, _ = existing
    if existing_team and team_id and existing_team != team_id:
        return False
    if (
        total_value is not None
        and incoming.total_value_cents is not None
        and total_value != incoming.total_value_cents
    ):
        return False
    return True


def _contract_row(cursor, contract_id: int) -> tuple[Any, ...]:
    cursor.execute(
        """SELECT id,signing_team_id,source_id,external_id,start_season,
                  end_season,term_years,contract_type,total_value_cents,
                  average_value_cents,is_entry_level
             FROM contracts
            WHERE id=%s""",
        (contract_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise MissingContractError(contract_id=contract_id)
    return row


@dataclass(frozen=True)
class _ResolvedContract:
    contract_id: int | None
    existing_seasons: dict[int, tuple[int, int]]


def _average_value(contract: ParsedContract) -> int | None:
    if contract.total_value_cents is None:
        return None
    return contract.total_value_cents // contract.term_years


def _record_conflict(summary: Counter[str]) -> None:
    summary["reconciliation_conflicts"] += 1
    summary["records_skipped"] += 1


def _matching_contract_id(
    cursor,
    *,
    player_id: int,
    source_id: int,
    contract: ParsedContract,
    signing_team_id: int | None,
    start: int,
    end: int,
) -> tuple[int | None, bool]:
    cursor.execute(
        "SELECT id FROM contracts WHERE source_id=%s AND external_id=%s",
        (source_id, contract.external_id),
    )
    source_match = cursor.fetchone()
    if source_match:
        return int(source_match[0]), False

    cursor.execute(
        """SELECT id
             FROM contracts
            WHERE player_id=%s AND start_season=%s AND end_season=%s
              AND term_years=%s""",
        (player_id, start, end, contract.term_years),
    )
    matches = [int(row[0]) for row in cursor.fetchall()]
    compatible = [
        contract_id
        for contract_id in matches
        if _compatible(_contract_row(cursor, contract_id), contract, signing_team_id)
    ]
    conflict = len(matches) > 1 or bool(matches and not compatible)
    return (compatible[0] if compatible else None), conflict


def _existing_contract_seasons(
    cursor,
    contract_id: int,
    seasons: Iterable[ContractSeason],
) -> dict[int, tuple[int, int]]:
    cursor.execute(
        """SELECT id,season_start_year,cap_hit_cents
             FROM contract_seasons
            WHERE contract_id=%s AND season_start_year = ANY(%s)""",
        (contract_id, [row.season_start_year for row in seasons]),
    )
    return {
        int(season): (int(season_id), cap_hit)
        for season_id, season, cap_hit in cursor.fetchall()
    }


def _resolve_contract(
    cursor,
    *,
    player_id: int,
    source_id: int,
    contract: ParsedContract,
    signing_team_id: int | None,
    start: int,
    end: int,
    seasons_to_write: tuple[ContractSeason, ...],
    summary: Counter[str],
    preview: bool,
) -> _ResolvedContract | None:
    contract_id, conflict = _matching_contract_id(
        cursor,
        player_id=player_id,
        source_id=source_id,
        contract=contract,
        signing_team_id=signing_team_id,
        start=start,
        end=end,
    )
    if conflict:
        _record_conflict(summary)
        return None

    existing_seasons: dict[int, tuple[int, int]] = {}
    if contract_id is not None:
        existing = _contract_row(cursor, contract_id)
        if not _compatible(existing, contract, signing_team_id):
            _record_conflict(summary)
            return None
        existing_seasons = _existing_contract_seasons(
            cursor, contract_id, seasons_to_write
        )
        if any(
            existing_seasons.get(row.season_start_year, (0, None))[1]
            not in (None, row.cap_hit_cents)
            for row in seasons_to_write
        ):
            _record_conflict(summary)
            return None
        summary["contracts_matched"] += 1
        if not preview:
            cursor.execute(
                """UPDATE contracts
                      SET signed_on=COALESCE(signed_on,%s),
                          signing_team_id=COALESCE(signing_team_id,%s),
                          contract_type=COALESCE(contract_type,%s),
                          expiry_status=COALESCE(expiry_status,%s),
                          total_value_cents=COALESCE(total_value_cents,%s),
                          average_value_cents=COALESCE(average_value_cents,%s),
                          source_payload=CASE
                              WHEN source_payload='{}'::jsonb THEN %s
                              ELSE source_payload END,
                          updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s""",
                (
                    contract.signed_on,
                    signing_team_id,
                    contract.contract_type,
                    contract.expiry_status,
                    contract.total_value_cents,
                    _average_value(contract),
                    Json(contract.source_payload or {}),
                    contract_id,
                ),
            )
        return _ResolvedContract(contract_id, existing_seasons)

    summary["contracts_created"] += 1
    if not preview:
        cursor.execute(
            """INSERT INTO contracts
                   (player_id,signing_team_id,source_id,external_id,signed_on,
                    start_season,end_season,term_years,contract_type,
                    expiry_status,total_value_cents,average_value_cents,
                    is_entry_level,source_payload)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id""",
            (
                player_id,
                signing_team_id,
                source_id,
                contract.external_id,
                contract.signed_on,
                start,
                end,
                contract.term_years,
                contract.contract_type,
                contract.expiry_status,
                contract.total_value_cents,
                _average_value(contract),
                contract.is_entry_level,
                Json(contract.source_payload or {}),
            ),
        )
        contract_id = int(cursor.fetchone()[0])
    return _ResolvedContract(contract_id, existing_seasons)


def _persist_contracts(
    cursor,
    player_id: int,
    nhl_id: str,
    contracts: Iterable[ParsedContract],
    first_season: int,
    last_season: int,
    source_id: int,
    summary: Counter[str],
    *,
    target_seasons: Iterable[int] | None = None,
    preview: bool = False,
    source_code: str = CAPSPACE_SOURCE,
    context: _PersistenceContext | None = None,
) -> None:
    persistence = context or _load_persistence_context(
        cursor, first_season, last_season
    )
    season_caps = persistence.season_caps
    available = set(season_caps)
    team_lookup = persistence.team_lookup
    stint_teams = {} if preview else _player_stint_teams(cursor, player_id)
    targets = set(target_seasons) if target_seasons is not None else None
    pending_seasons: list[tuple[Any, ...]] = []
    for contract in normalize_contracts(contracts, nhl_id, source_code):
        seasons = tuple(
            row
            for row in contract.seasons
            if row.season_start_year in available
            and first_season - 10 <= row.season_start_year <= last_season
        )
        if not seasons:
            summary["records_skipped"] += 1
            continue
        seasons_to_write = tuple(
            row
            for row in seasons
            if targets is None or row.season_start_year in targets
        )
        if not seasons_to_write:
            continue
        start = min(row.season_start_year for row in seasons)
        end = max(row.season_start_year for row in seasons)
        signing_team_id = team_lookup.get(_clean_text(contract.signing_team).casefold())
        resolved = _resolve_contract(
            cursor,
            player_id=player_id,
            source_id=source_id,
            contract=contract,
            signing_team_id=signing_team_id,
            start=start,
            end=end,
            seasons_to_write=seasons_to_write,
            summary=summary,
            preview=preview,
        )
        if resolved is None:
            continue
        contract_id = resolved.contract_id
        existing_seasons = resolved.existing_seasons
        if preview:
            summary["contract_seasons_updated"] += sum(
                row.season_start_year in existing_seasons for row in seasons_to_write
            )
            summary["contract_seasons_created"] += sum(
                row.season_start_year not in existing_seasons
                for row in seasons_to_write
            )
            continue
        for row in seasons_to_write:
            owning_team_id = _resolve_team_id(
                team_lookup,
                stint_teams,
                row.season_start_year,
                row.owning_team,
            )
            base = row.base_salary_cents
            total_cash = (
                base + row.signing_bonus_cents
                if base is not None and row.signing_bonus_cents is not None
                else base
            )
            cap = season_caps[row.season_start_year]
            cap_pct = Decimal(row.cap_hit_cents) / Decimal(cap) if cap else None
            existing_season = existing_seasons.get(row.season_start_year)
            if existing_season:
                existing_season_id, existing_cap_hit = existing_season
                if existing_cap_hit != row.cap_hit_cents:
                    summary["reconciliation_conflicts"] += 1
                    continue
                cursor.execute(
                    """UPDATE contract_seasons SET owning_team_id=COALESCE(owning_team_id,%s), base_salary_cents=COALESCE(base_salary_cents,%s), signing_bonus_cents=COALESCE(signing_bonus_cents,%s), performance_bonus_cents=COALESCE(performance_bonus_cents,%s), total_cash_cents=COALESCE(total_cash_cents,%s), cap_percentage=COALESCE(cap_percentage,%s), clauses=CASE WHEN clauses='{}'::jsonb THEN %s ELSE clauses END, is_slide=is_slide OR %s, updated_at=CURRENT_TIMESTAMP WHERE id=%s""",
                    (
                        owning_team_id,
                        base,
                        row.signing_bonus_cents,
                        row.performance_bonus_cents,
                        total_cash,
                        cap_pct,
                        Json(
                            {
                                "clause": row.clause,
                                "minors_salary_cents": row.minors_salary_cents,
                                "source": source_code,
                            }
                        ),
                        row.is_slide,
                        existing_season_id,
                    ),
                )
                summary["contract_seasons_updated"] += 1
            else:
                pending_seasons.append(
                    (
                        contract_id,
                        row.season_start_year,
                        owning_team_id,
                        base,
                        row.signing_bonus_cents,
                        row.performance_bonus_cents,
                        total_cash,
                        row.cap_hit_cents,
                        cap_pct,
                        row.is_slide,
                        Json(
                            {
                                "clause": row.clause,
                                "minors_salary_cents": row.minors_salary_cents,
                                "source": source_code,
                            }
                        ),
                    )
                )
    if pending_seasons:
        execute_values(
            cursor,
            """INSERT INTO contract_seasons (contract_id,season_start_year,owning_team_id,base_salary_cents,signing_bonus_cents,performance_bonus_cents,total_cash_cents,cap_hit_cents,cap_percentage,is_slide,clauses)
            VALUES %s""",
            pending_seasons,
            page_size=500,
        )
        summary["contract_seasons_created"] += len(pending_seasons)


def _source_record_values(
    source_id: int, source_code: str, candidate: Candidate, payload: dict[str, Any]
) -> tuple[Any, ...]:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    safe_payload = json.loads(encoded)
    return (
        source_id,
        f"{source_code}_player_profile",
        candidate.nhl_id or str(candidate.player_id),
        hashlib.sha256(encoded.encode()).hexdigest(),
        Json(safe_payload),
    )


def _source_records_bulk(
    cursor,
    source_id: int,
    source_code: str,
    records: Iterable[tuple[Candidate, dict[str, Any]]],
) -> None:
    values = [
        _source_record_values(source_id, source_code, candidate, payload)
        for candidate, payload in records
    ]
    if not values:
        return
    execute_values(
        cursor,
        """INSERT INTO source_records (source_id,entity_type,external_key,payload_hash,payload)
        VALUES %s ON CONFLICT (source_id,entity_type,external_key,payload_hash) DO NOTHING""",
        values,
        page_size=500,
    )


def _fetch_profile(
    session: ProfileSession, candidate: Candidate, *, max_attempts: int = 4
) -> ProfileResult:
    if not candidate.nhl_id:
        return ProfileResult(
            candidate=candidate,
            url="",
            outcome=ContractsAbsent(reason=AbsenceReason.NO_NHL_ID, detail=None),
        )
    url = f"{CAPSPACE_BASE_URL}/person/nhl:{candidate.nhl_id}"
    for attempt in range(max_attempts):
        try:
            response = session.get(url, timeout=30)
        except requests.RequestException as exc:
            if attempt + 1 == max_attempts:
                return ProfileResult(
                    candidate=candidate,
                    url=url,
                    outcome=ProfileFailure(
                        reason=FailureReason.FAILED,
                        detail="timeout"
                        if isinstance(exc, requests.Timeout)
                        else str(exc),
                    ),
                )
            time.sleep(min(2**attempt, 8))
            continue
        if response.status_code == 404:
            return ProfileResult(
                candidate=candidate,
                url=url,
                outcome=ContractsAbsent(reason=AbsenceReason.NOT_FOUND, detail=None),
            )
        if response.status_code == 200:
            returned_url = getattr(response, "url", "")
            if (
                isinstance(returned_url, str)
                and returned_url
                and urlsplit(returned_url).path.rstrip("/")
                != f"/person/nhl:{candidate.nhl_id}"
            ):
                return ProfileResult(
                    candidate=candidate,
                    url=url,
                    html=response.text,
                    outcome=ProfileFailure(
                        reason=FailureReason.PARSE_FAILED,
                        detail="CapSpace redirected to a different player identity",
                    ),
                )
            try:
                contracts = parse_capspace_page(
                    response.text, expected_nhl_id=candidate.nhl_id
                )
            except CapSpaceError as exc:
                return ProfileResult(
                    candidate=candidate,
                    url=url,
                    html=response.text,
                    outcome=ProfileFailure(
                        reason=FailureReason.PARSE_FAILED, detail=str(exc)
                    ),
                )
            return parsed_profile(
                candidate=candidate, url=url, html=response.text, contracts=contracts
            )
        retryable = response.status_code in RETRYABLE_HTTP_STATUSES
        if not retryable or attempt + 1 == max_attempts:
            return ProfileResult(
                candidate=candidate,
                url=url,
                outcome=ProfileFailure(
                    reason=FailureReason.FAILED, detail=f"HTTP {response.status_code}"
                ),
            )
        retry_after = response.headers.get("Retry-After")
        try:
            delay = min(float(retry_after), 30) if retry_after else min(2**attempt, 8)
        except ValueError:
            delay = min(2**attempt, 8)
        time.sleep(delay)
    return ProfileResult(
        candidate=candidate,
        url=url,
        outcome=ProfileFailure(reason=FailureReason.FAILED, detail="retry exhaustion"),
    )


def _target_seasons_covered(result: ProfileResult) -> set[int]:
    """Backward-compatible helper for callers that need a mutable set."""
    return set(result.target_seasons_covered)


def _capwages_identity_matches(
    html: str,
    candidate: Candidate,
    url: str,
) -> bool:
    return _capwages_document_matches(parse_source_document(html), candidate, url)


def _fetch_capwages_profile(
    session: ProfileSession,
    candidate: Candidate,
) -> ProfileResult:
    """Try CapWages slugs with strong identity checks and bounded requests."""
    if not candidate.nhl_id:
        return ProfileResult(
            candidate=candidate,
            url="",
            source_code=CAPWAGES_SOURCE,
            outcome=ContractsAbsent(reason=AbsenceReason.NO_NHL_ID, detail=None),
        )
    slug = _slug_from_name(f"{candidate.first_name} {candidate.last_name}")
    if not slug:
        return ProfileResult(
            candidate=candidate,
            url="",
            source_code=CAPWAGES_SOURCE,
            outcome=ContractsAbsent(
                reason=AbsenceReason.NOT_FOUND,
                detail="player name cannot form a CapWages slug",
            ),
        )
    last_result: ProfileResult | None = None
    for suffix in CAPWAGES_SLUG_SUFFIXES:
        url = f"{CAPWAGES_BASE_URL}/players/{slug}{suffix}"
        try:
            response = session.get(url, timeout=30)
        except requests.RequestException as exc:
            last_result = ProfileResult(
                candidate=candidate,
                url=url,
                source_code=CAPWAGES_SOURCE,
                outcome=ProfileFailure(
                    reason=FailureReason.FAILED,
                    detail="timeout" if isinstance(exc, requests.Timeout) else str(exc),
                ),
            )
            continue
        if response.status_code == 404 and not suffix:
            # Numbered slugs only exist to disambiguate a base slug already
            # owned by a same-name player. Avoid three guaranteed misses for
            # every historical candidate absent from CapWages.
            return ProfileResult(
                candidate=candidate,
                url=url,
                source_code=CAPWAGES_SOURCE,
                outcome=ContractsAbsent(reason=AbsenceReason.NOT_FOUND, detail=None),
            )
        if response.status_code == 404:
            continue
        if response.status_code != 200:
            # A rate-limit or source outage applies to the host, not just this
            # guessed slug. Stop rather than multiplying requests.
            return ProfileResult(
                candidate=candidate,
                url=url,
                source_code=CAPWAGES_SOURCE,
                outcome=ProfileFailure(
                    reason=FailureReason.FAILED, detail=f"HTTP {response.status_code}"
                ),
            )
        document = parse_source_document(response.text)
        if not _capwages_document_matches(document, candidate, url):
            last_result = ProfileResult(
                candidate=candidate,
                url=url,
                html=response.text,
                source_code=CAPWAGES_SOURCE,
                outcome=ProfileFailure(
                    reason=FailureReason.PARSE_FAILED,
                    detail="CapWages profile identity could not be validated",
                ),
            )
            continue
        try:
            contracts = _parse_contract_document(
                document,
                expected_nhl_id=candidate.nhl_id,
            )
        except CapSpaceError as exc:
            last_result = ProfileResult(
                candidate=candidate,
                url=url,
                html=response.text,
                source_code=CAPWAGES_SOURCE,
                outcome=ProfileFailure(
                    reason=FailureReason.PARSE_FAILED, detail=str(exc)
                ),
            )
            return last_result
        result = parsed_profile(
            candidate=candidate,
            url=url,
            html=response.text,
            source_code=CAPWAGES_SOURCE,
            contracts=contracts,
        )
        if result.covers_target:
            return result
        return result
    return last_result or ProfileResult(
        candidate=candidate,
        url=f"{CAPWAGES_BASE_URL}/players/{slug}",
        source_code=CAPWAGES_SOURCE,
        outcome=ContractsAbsent(reason=AbsenceReason.NOT_FOUND, detail=None),
    )


def _fetch_profile_with_fallback(
    session: ProfileSession,
    candidate: Candidate,
) -> ProfileResult:
    primary = _fetch_profile(session, candidate)
    if primary.covers_target or not candidate.nhl_id:
        return primary
    fallback = _fetch_capwages_profile(session, candidate)
    if fallback.covers_target:
        return replace(
            fallback,
            fallback_attempted=True,
            primary_status=primary.status,
            fallback_status=fallback.status,
        )
    return replace(
        primary,
        fallback_attempted=True,
        primary_status=primary.status,
        fallback_status=fallback.status,
    )


def _candidate_snapshot(**kwargs: Any) -> tuple[list[Candidate], dict[str, Any]]:
    with database_transaction() as connection:
        cursor = connection.cursor()
        candidates = select_candidates(cursor, **kwargs)
        cursor.close()
    return candidates, {
        "candidate_player_seasons": sum(
            len(item.missing_seasons) for item in candidates
        ),
        "candidate_players": len(candidates),
    }


def _fetch_profiles(
    session: ProfileSession, candidates: list[Candidate], workers: int
) -> list[ProfileResult]:
    results: list[ProfileResult] = []
    with ThreadPoolExecutor(
        max_workers=min(workers, max(1, len(candidates)))
    ) as executor:
        futures = {
            executor.submit(_fetch_profile_with_fallback, session, candidate): candidate
            for candidate in candidates
            if candidate.nhl_id
        }
        for future in as_completed(futures):
            results.append(future.result())
    return results


def _result_source_payload(result: ProfileResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "error": result.error,
        "url": result.url,
        "contracts": [serialize_contract(contract) for contract in result.contracts],
    }


def _source_records_by_code(
    candidates: Iterable[Candidate],
    results: Iterable[ProfileResult],
) -> dict[str, list[tuple[Candidate, dict[str, Any]]]]:
    grouped: dict[str, list[tuple[Candidate, dict[str, Any]]]] = {
        CAPSPACE_SOURCE: [
            (candidate, {"status": STATUS_NO_NHL_ID})
            for candidate in candidates
            if candidate.nhl_id is None
        ]
    }
    for result in results:
        grouped.setdefault(result.source_code, []).append(
            (result.candidate, _result_source_payload(result))
        )
    return grouped


def _persist_successful_results(
    cursor,
    results: Iterable[ProfileResult],
    source_ids: dict[str, int],
    summary: Counter[str],
    context: _PersistenceContext,
    *,
    first_season: int,
    last_season: int,
    preview: bool,
) -> None:
    for result in results:
        if result.status != STATUS_SUCCEEDED:
            continue
        _persist_contracts(
            cursor,
            result.candidate.player_id,
            result.candidate.nhl_id or "",
            result.contracts,
            first_season,
            last_season,
            source_ids[result.source_code],
            summary,
            target_seasons=result.candidate.missing_seasons,
            preview=preview,
            source_code=result.source_code,
            context=context,
        )


def _persist_batch(
    candidates: list[Candidate],
    results: list[ProfileResult],
    *,
    dry_run: bool,
    first_season: int,
    last_season: int,
) -> Counter[str]:
    batch_summary: Counter[str] = Counter()
    with database_transaction() as connection:
        cursor = connection.cursor()
        source_ids: dict[str, int] = {
            source_code: _source_id(cursor, source_code)
            for source_code in {result.source_code for result in results}
            | {CAPSPACE_SOURCE}
        }
        if not dry_run:
            for source_code, source_records in _source_records_by_code(
                candidates, results
            ).items():
                _source_records_bulk(
                    cursor,
                    source_ids[source_code],
                    source_code,
                    source_records,
                )
        successful_results = [
            result for result in results if result.status == STATUS_SUCCEEDED
        ]
        if successful_results:
            context = _load_persistence_context(cursor, first_season, last_season)
            _persist_successful_results(
                cursor,
                successful_results,
                source_ids,
                batch_summary,
                context,
                first_season=first_season,
                last_season=last_season,
                preview=dry_run,
            )
        cursor.close()
    return batch_summary


def _profile_metrics(results: Iterable[ProfileResult]) -> Counter[str]:
    materialized = list(results)
    return Counter(
        {
            "profiles_succeeded": sum(
                result.status == STATUS_SUCCEEDED for result in materialized
            ),
            "profiles_with_target_coverage": sum(
                result.covers_target for result in materialized
            ),
            "profiles_not_found": sum(
                result.status == STATUS_NOT_FOUND for result in materialized
            ),
            "profiles_failed": sum(
                result.status in FAILURE_STATUSES for result in materialized
            ),
            "profiles_no_contracts": sum(
                result.status == STATUS_NO_CONTRACTS for result in materialized
            ),
            "profiles_no_matching_contracts": sum(
                result.status == STATUS_NO_MATCHING_CONTRACTS for result in materialized
            ),
            "capspace_profiles_succeeded": sum(
                result.status == STATUS_SUCCEEDED
                and result.source_code == CAPSPACE_SOURCE
                for result in materialized
            ),
            "capwages_profiles_succeeded": sum(
                result.status == STATUS_SUCCEEDED
                and result.source_code == CAPWAGES_SOURCE
                for result in materialized
            ),
            "capwages_fallbacks_attempted": sum(
                result.fallback_attempted for result in materialized
            ),
            "capwages_fallbacks_failed": sum(
                result.fallback_status in FAILURE_STATUSES for result in materialized
            ),
            "capwages_fallbacks_not_found": sum(
                result.fallback_status == STATUS_NOT_FOUND for result in materialized
            ),
            "contracts_parsed": sum(len(result.contracts) for result in materialized),
        }
    )


def _unprocessed_count(summary: dict[str, Any]) -> int:
    return (
        summary.get("records_skipped", 0)
        + summary.get("players_without_nhl_ids", 0)
        + summary.get("profiles_failed", 0)
        + summary.get("profiles_not_found", 0)
    )


def _run(
    session: ProfileSession,
    *,
    dry_run: bool,
    first_season: int = DEFAULT_FIRST_SEASON,
    last_season: int = DEFAULT_LAST_SEASON,
    limit: int | None = None,
    workers: int = 4,
    batch_size: int = DEFAULT_BATCH_SIZE,
    player_id: int | None = None,
    nhl_id: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"workers must be between 1 and {MAX_WORKERS}")
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
    candidates, summary = _candidate_snapshot(
        first_season=first_season,
        last_season=last_season,
        limit=limit,
        player_id=player_id,
        nhl_id=nhl_id,
        force=force,
    )
    summary.update(
        {
            "players_without_nhl_ids": sum(item.nhl_id is None for item in candidates),
            "profiles_requested": sum(item.nhl_id is not None for item in candidates),
        }
    )
    if not candidates:
        summary.update(
            records_read=0,
            records_created=0,
            records_updated=0,
            records_skipped=0,
            remaining_uncovered_player_seasons=0,
        )
        return summary
    aggregate = Counter()
    total_results = 0
    for offset in range(0, len(candidates), batch_size):
        batch = candidates[offset : offset + batch_size]
        results = _fetch_profiles(session, batch, workers)
        total_results += len(results)
        aggregate.update(_profile_metrics(results))
        aggregate.update(
            _persist_batch(
                batch,
                results,
                dry_run=dry_run,
                first_season=first_season,
                last_season=last_season,
            )
        )
        aggregate["batches_processed"] += 1
    summary.update(dict(aggregate))
    summary["profiles_requested"] = total_results
    if dry_run:
        summary.update(
            {
                "proposed_contracts": summary.get("contracts_parsed", 0),
                "records_read": summary["candidate_player_seasons"],
                "records_created": 0,
                "records_updated": 0,
            }
        )
        summary["records_skipped"] = _unprocessed_count(summary)
        return summary
    summary["records_read"] = (
        summary["candidate_player_seasons"] + summary["contracts_parsed"]
    )
    summary["records_created"] = summary.get("contracts_created", 0) + summary.get(
        "contract_seasons_created", 0
    )
    summary["records_updated"] = summary.get("contracts_matched", 0) + summary.get(
        "contract_seasons_updated", 0
    )
    summary["records_skipped"] = _unprocessed_count(summary)
    with database_transaction() as connection:
        cursor = connection.cursor()
        coverage = _coverage_counts(cursor, first_season, last_season)
        summary["remaining_uncovered_player_seasons"] = coverage[
            "missing_player_seasons"
        ]
        cursor.close()
    return summary


def _source_id(cursor, source_code: str = CAPSPACE_SOURCE) -> int:
    cursor.execute("SELECT id FROM data_sources WHERE code=%s", (source_code,))
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(
            f"{source_code} source is not registered; run Alembic upgrade head"
        )
    return int(row[0])


def _coverage_counts(cursor, first_season: int, last_season: int) -> dict[str, Any]:
    cursor.execute(
        f"""WITH {STAT_SEASONS_CTE}
            SELECT count(*),
                   count(*) FILTER (WHERE NOT ({MISSING_CONTRACT_PREDICATE}))
              FROM stat_seasons s""",
        (first_season, last_season, first_season, last_season),
    )
    total, covered = cursor.fetchone()
    return {
        "total_player_seasons": total,
        "covered_player_seasons": covered,
        "missing_player_seasons": total - covered,
        "coverage_pct": round(covered * 100 / total, 2) if total else None,
    }


def coverage_report(
    *, first_season: int = DEFAULT_FIRST_SEASON, last_season: int = DEFAULT_LAST_SEASON
) -> dict[str, Any]:
    with database_transaction() as connection:
        cursor = connection.cursor()
        report = _coverage_counts(cursor, first_season, last_season)
        range_params = (first_season, last_season, first_season, last_season)
        cursor.execute(
            f"""WITH {STAT_SEASONS_CTE}
                SELECT season_start_year,count(*)
                  FROM stat_seasons s
                 WHERE {MISSING_CONTRACT_PREDICATE}
                 GROUP BY season_start_year
                 ORDER BY season_start_year""",
            range_params,
        )
        report["missing_by_season"] = {row[0]: row[1] for row in cursor.fetchall()}
        cursor.execute(
            f"""WITH {STAT_SEASONS_CTE}
                SELECT p.id,p.first_name || ' ' || p.last_name,count(*)
                  FROM stat_seasons s
                  JOIN players p ON p.id=s.player_id
                 WHERE {MISSING_CONTRACT_PREDICATE}
                 GROUP BY p.id,p.first_name,p.last_name
                 ORDER BY count(*) DESC,p.id""",
            range_params,
        )
        report["missing_by_player"] = [
            {"player_id": row[0], "player": row[1], "count": row[2]}
            for row in cursor.fetchall()
        ]
        cursor.execute("""SELECT ds.code,payload->>'status',count(*)
            FROM source_records sr JOIN data_sources ds ON ds.id=sr.source_id
            WHERE (ds.code='capspace' AND sr.entity_type='capspace_player_profile')
               OR (ds.code='capwages' AND sr.entity_type='capwages_player_profile')
            GROUP BY ds.code,payload->>'status'""")
        source_outcomes: dict[str, dict[str, int]] = {}
        for source_code, status, count in cursor.fetchall():
            source_outcomes.setdefault(source_code, {})[status] = count
        report["source_outcomes"] = source_outcomes
        cursor.close()
    return report


@tracked_ingestion(CAPSPACE_SOURCE, "populate_historical_contracts")
def ingest_historical_contracts(
    session: ProfileSession, **kwargs: Any
) -> dict[str, Any]:
    return _run(session, dry_run=False, **kwargs)


def preview_historical_contracts(
    session: ProfileSession, **kwargs: Any
) -> dict[str, Any]:
    return _run(session, dry_run=True, **kwargs)


def existing_historical_contract_summary() -> dict[str, Any]:
    report = coverage_report()
    report.update(
        {
            "cached": 1,
            "records_read": report["total_player_seasons"],
            "records_created": 0,
            "records_updated": 0,
            "records_skipped": 0,
        }
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gap-fill historical NHL contracts from CapSpace and CapWages"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="preview without contract/source-record mutations",
    )
    mode.add_argument("--apply", action="store_true", help="persist the backfill")
    mode.add_argument(
        "--coverage",
        action="store_true",
        help="print current historical contract coverage and exit",
    )
    parser.add_argument("--nhl-id")
    parser.add_argument("--player-id", type=int)
    parser.add_argument("--first-season", type=int, default=DEFAULT_FIRST_SEASON)
    parser.add_argument("--last-season", type=int, default=DEFAULT_LAST_SEASON)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"players fetched and committed per batch (1-{MAX_BATCH_SIZE})",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    init_db()
    if args.coverage:
        print(
            json.dumps(
                coverage_report(
                    first_season=args.first_season, last_season=args.last_season
                ),
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
        return 0
    session = http_session()
    options = {
        "first_season": args.first_season,
        "last_season": args.last_season,
        "limit": args.limit,
        "workers": args.workers,
        "batch_size": args.batch_size,
        "player_id": args.player_id,
        "nhl_id": args.nhl_id,
        "force": args.force,
    }
    summary = (
        ingest_historical_contracts(session, **options)
        if args.apply
        else preview_historical_contracts(session, **options)
    )
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

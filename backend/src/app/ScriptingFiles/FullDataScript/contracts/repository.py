"""PostgreSQL candidate selection, reconciliation, snapshots, and coverage."""

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Generator, Iterable, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from app.database import open_database_transaction
from app.shared.observability.domain import DiagnosticContext
from app.ScriptingFiles.FullDataScript.contracts.domain import (
    Candidate,
    ContractSeason,
    ParsedContract,
    ProfileResult,
    ProfileSource,
    ProfileStatus,
    StoredContract,
)
from app.ScriptingFiles.FullDataScript.contracts.errors import (
    MissingContractError,
    MissingContractSourceError,
)
from app.ScriptingFiles.FullDataScript.contracts.options import (
    HistoricalContractOptions,
    find_option_violation,
)
from app.ScriptingFiles.FullDataScript.contracts.policy import (
    ContractReconciliationPolicy,
    are_contracts_compatible,
)
from app.ScriptingFiles.FullDataScript.contracts.reporting import group_source_records
from app.ScriptingFiles.FullDataScript.contracts.schemas.contracts import (
    normalize_contracts,
)
from app.ScriptingFiles.FullDataScript.contracts.util import clean_text as _clean_text
from psycopg2.extensions import cursor as PgCursor
from psycopg2.extras import Json, execute_values

DEFAULT_FIRST_SEASON = HistoricalContractOptions().first_season
DEFAULT_LAST_SEASON = HistoricalContractOptions().last_season
CAPSPACE_SOURCE = ProfileSource.CAPSPACE

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
    cursor: PgCursor,
    *,
    first_season: int = DEFAULT_FIRST_SEASON,
    last_season: int = DEFAULT_LAST_SEASON,
    player_id: int | None = None,
    nhl_id: str | None = None,
    limit: int | None = None,
    force: bool = False,
) -> list[Candidate]:
    filters = []
    params: list[object] = [
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
    where_clause = " AND ".join(filters) if len(filters) > 0 else "TRUE"
    limit_sql = " LIMIT %s" if limit is not None else ""
    if limit is not None:
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
            nhl_id=str(row[3]) if row[3] not in (None, "") else None,
            missing_seasons=tuple(row[4]),
        )
        for row in cursor.fetchall()
    ]


def load_team_lookup(cursor: PgCursor) -> dict[str, int]:
    cursor.execute("SELECT id,abbreviation,name FROM teams")
    lookup: dict[str, int] = {}
    for team_id, abbreviation, name in cursor.fetchall():
        for value in (abbreviation, name):
            key = _clean_text(value).casefold()
            if key != "":
                lookup[key] = int(team_id)
    return lookup


@dataclass(slots=True, kw_only=True, frozen=True)
class PersistenceContext:
    season_caps: Mapping[int, int | None]
    team_lookup: Mapping[str, int]


def load_persistence_context(
    cursor: PgCursor,
    first_season: int,
    last_season: int,
) -> PersistenceContext:
    cursor.execute(
        """SELECT start_year,salary_cap_cents
             FROM seasons
            WHERE start_year BETWEEN %s AND %s""",
        (first_season - 10, last_season),
    )
    return PersistenceContext(
        season_caps=MappingProxyType(
            {int(year): cap for year, cap in cursor.fetchall()}
        ),
        team_lookup=MappingProxyType(load_team_lookup(cursor)),
    )


def load_player_stint_teams(
    cursor: PgCursor, player_id: int
) -> dict[int, tuple[int, ...]]:
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


def resolve_team_id(
    team_lookup: Mapping[str, int],
    stint_teams: dict[int, tuple[int, ...]],
    season: int,
    explicit: str | None,
) -> int | None:
    explicit_id = team_lookup.get(_clean_text(explicit).casefold())
    if explicit_id is not None:
        return explicit_id
    teams = stint_teams.get(season, ())
    return teams[0] if len(teams) == 1 else None


def build_contract_row(cursor: PgCursor, contract_id: int) -> StoredContract:
    cursor.execute(
        """SELECT id,player_id,signing_team_id,total_value_cents
             FROM contracts
            WHERE id=%s""",
        (contract_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise MissingContractError(contract_id=contract_id)
    return StoredContract(
        contract_id=row[0],
        player_id=row[1],
        signing_team_id=row[2],
        total_value_cents=row[3],
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ResolvedContract:
    contract_id: int | None
    existing_seasons: Mapping[int, tuple[int, int]]


def calculate_average_value(contract: ParsedContract) -> int | None:
    if contract.total_value_cents is None:
        return None
    return contract.total_value_cents // contract.term_years


def record_conflict(summary: Counter[str]) -> None:
    summary["reconciliation_conflicts"] += 1
    summary["records_skipped"] += 1


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractWriteContext:
    player_id: int
    source_id: int
    contract: ParsedContract
    signing_team_id: int | None
    seasons: tuple[ContractSeason, ...]
    seasons_to_write: tuple[ContractSeason, ...]

    @property
    def start(self) -> int:
        return min(row.season_start_year for row in self.seasons)

    @property
    def end(self) -> int:
        return max(row.season_start_year for row in self.seasons)


def find_matching_contract_id(
    cursor: PgCursor,
    context: ContractWriteContext,
) -> tuple[int | None, bool]:
    cursor.execute(
        "SELECT id FROM contracts WHERE source_id=%s AND external_id=%s",
        (context.source_id, context.contract.external_id),
    )
    source_match = cursor.fetchone()
    policy = ContractReconciliationPolicy(
        player_id=context.player_id,
        incoming=context.contract,
        signing_team_id=context.signing_team_id,
    )
    if source_match is not None:
        existing = build_contract_row(cursor, int(source_match[0]))
        return existing.contract_id, policy.find_violation((existing,)) is not None

    cursor.execute(
        """SELECT id
             FROM contracts
            WHERE player_id=%s AND start_season=%s AND end_season=%s
              AND term_years=%s""",
        (context.player_id, context.start, context.end, context.contract.term_years),
    )
    matches = tuple(
        build_contract_row(cursor, int(row[0])) for row in cursor.fetchall()
    )
    conflict = policy.find_violation(matches) is not None
    return (matches[0].contract_id if len(matches) == 1 else None), conflict


def load_contract_seasons(
    cursor: PgCursor,
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


def resolve_contract(
    cursor: PgCursor,
    context: ContractWriteContext,
    *,
    summary: Counter[str],
    preview: bool,
) -> ResolvedContract | None:
    contract = context.contract
    contract_id, conflict = find_matching_contract_id(cursor, context)
    if conflict:
        record_conflict(summary)
        return None

    existing_seasons: dict[int, tuple[int, int]] = {}
    if contract_id is not None:
        existing = build_contract_row(cursor, contract_id)
        if not are_contracts_compatible(existing, contract, context.signing_team_id):
            record_conflict(summary)
            return None
        existing_seasons = load_contract_seasons(
            cursor, contract_id, context.seasons_to_write
        )
        if any(
            existing_seasons.get(row.season_start_year, (0, None))[1]
            not in (None, row.cap_hit_cents)
            for row in context.seasons_to_write
        ):
            record_conflict(summary)
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
                    context.signing_team_id,
                    contract.contract_type,
                    contract.expiry_status,
                    contract.total_value_cents,
                    calculate_average_value(contract),
                    Json(
                        payload
                        if (payload := contract.source_payload) is not None
                        else {}
                    ),
                    contract_id,
                ),
            )
        return ResolvedContract(
            contract_id=contract_id, existing_seasons=MappingProxyType(existing_seasons)
        )

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
                context.player_id,
                context.signing_team_id,
                context.source_id,
                contract.external_id,
                contract.signed_on,
                context.start,
                context.end,
                contract.term_years,
                contract.contract_type,
                contract.expiry_status,
                contract.total_value_cents,
                calculate_average_value(contract),
                contract.is_entry_level,
                Json(
                    payload if (payload := contract.source_payload) is not None else {}
                ),
            ),
        )
        contract_id = int(cursor.fetchone()[0])
    return ResolvedContract(
        contract_id=contract_id, existing_seasons=MappingProxyType(existing_seasons)
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SeasonWrite:
    contract_id: int
    season: ContractSeason
    owning_team_id: int | None
    cap_percentage: Decimal | None
    source_code: str

    @property
    def total_cash(self) -> int | None:
        base = self.season.base_salary_cents
        bonus = self.season.signing_bonus_cents
        return base + bonus if base is not None and bonus is not None else base

    @property
    def clauses(self) -> Json:
        return Json(
            {
                "clause": self.season.clause,
                "minors_salary_cents": self.season.minors_salary_cents,
                "source": self.source_code,
            }
        )

    @property
    def insert_values(self) -> tuple[object, ...]:
        return (
            self.contract_id,
            self.season.season_start_year,
            self.owning_team_id,
            self.season.base_salary_cents,
            self.season.signing_bonus_cents,
            self.season.performance_bonus_cents,
            self.total_cash,
            self.season.cap_hit_cents,
            self.cap_percentage,
            self.season.is_slide,
            self.clauses,
        )


def persist_season_write(
    cursor: PgCursor,
    write: SeasonWrite,
    existing: tuple[int, int] | None,
    summary: Counter[str],
    pending: list[tuple[object, ...]],
) -> None:
    if existing is None:
        pending.append(write.insert_values)
        return
    season_id, cap_hit = existing
    if cap_hit != write.season.cap_hit_cents:
        summary["reconciliation_conflicts"] += 1
        return
    cursor.execute(
        """UPDATE contract_seasons SET owning_team_id=COALESCE(owning_team_id,%s), base_salary_cents=COALESCE(base_salary_cents,%s), signing_bonus_cents=COALESCE(signing_bonus_cents,%s), performance_bonus_cents=COALESCE(performance_bonus_cents,%s), total_cash_cents=COALESCE(total_cash_cents,%s), cap_percentage=COALESCE(cap_percentage,%s), clauses=CASE WHEN clauses='{}'::jsonb THEN %s ELSE clauses END, is_slide=is_slide OR %s, updated_at=CURRENT_TIMESTAMP WHERE id=%s""",
        (
            write.owning_team_id,
            write.season.base_salary_cents,
            write.season.signing_bonus_cents,
            write.season.performance_bonus_cents,
            write.total_cash,
            write.cap_percentage,
            write.clauses,
            write.season.is_slide,
            season_id,
        ),
    )
    summary["contract_seasons_updated"] += 1


def persist_contracts(
    cursor: PgCursor,
    result: ProfileResult,
    options: HistoricalContractOptions,
    source_id: int,
    summary: Counter[str],
    *,
    preview: bool,
    context: PersistenceContext,
) -> None:
    player_id = result.candidate.player_id
    nhl_id = result.candidate.nhl_id
    assert nhl_id is not None
    contracts = result.contracts
    first_season = options.first_season
    last_season = options.last_season
    source_code = result.source_code
    persistence = context
    season_caps = persistence.season_caps
    available = set(season_caps)
    team_lookup = persistence.team_lookup
    stint_teams = {} if preview else load_player_stint_teams(cursor, player_id)
    targets = frozenset(result.candidate.missing_seasons)
    pending_seasons: list[tuple[object, ...]] = []
    for contract in normalize_contracts(contracts, nhl_id, source_code):
        seasons = tuple(
            row
            for row in contract.seasons
            if row.season_start_year in available
            and first_season - 10 <= row.season_start_year <= last_season
        )
        if len(seasons) == 0:
            summary["records_skipped"] += 1
            continue
        seasons_to_write = tuple(
            row for row in seasons if row.season_start_year in targets
        )
        if len(seasons_to_write) == 0:
            continue
        signing_team_id = team_lookup.get(_clean_text(contract.signing_team).casefold())
        resolved = resolve_contract(
            cursor,
            ContractWriteContext(
                player_id=player_id,
                source_id=source_id,
                contract=contract,
                signing_team_id=signing_team_id,
                seasons=seasons,
                seasons_to_write=seasons_to_write,
            ),
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
        assert contract_id is not None
        for row in seasons_to_write:
            cap = season_caps[row.season_start_year]
            write = SeasonWrite(
                contract_id=contract_id,
                season=row,
                owning_team_id=resolve_team_id(
                    team_lookup, stint_teams, row.season_start_year, row.owning_team
                ),
                cap_percentage=Decimal(row.cap_hit_cents) / Decimal(cap)
                if cap not in (None, 0)
                else None,
                source_code=source_code,
            )
            persist_season_write(
                cursor,
                write,
                existing_seasons.get(row.season_start_year),
                summary,
                pending_seasons,
            )
    if len(pending_seasons) > 0:
        execute_values(
            cursor,
            """INSERT INTO contract_seasons (contract_id,season_start_year,owning_team_id,base_salary_cents,signing_bonus_cents,performance_bonus_cents,total_cash_cents,cap_hit_cents,cap_percentage,is_slide,clauses)
            VALUES %s""",
            pending_seasons,
            page_size=500,
        )
        summary["contract_seasons_created"] += len(pending_seasons)


def build_source_record_values(
    source_id: int, source_code: str, candidate: Candidate, payload: dict[str, object]
) -> tuple[object, ...]:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    safe_payload = json.loads(encoded)
    return (
        source_id,
        f"{source_code}_player_profile",
        candidate.nhl_id if candidate.nhl_id is not None else str(candidate.player_id),
        hashlib.sha256(encoded.encode()).hexdigest(),
        Json(safe_payload),
    )


def save_source_records_bulk(
    cursor: PgCursor,
    source_id: int,
    source_code: str,
    records: Iterable[tuple[Candidate, dict[str, object]]],
) -> None:
    values = [
        build_source_record_values(source_id, source_code, candidate, payload)
        for candidate, payload in records
    ]
    if len(values) == 0:
        return
    execute_values(
        cursor,
        """INSERT INTO source_records (source_id,entity_type,external_key,payload_hash,payload)
        VALUES %s ON CONFLICT (source_id,entity_type,external_key,payload_hash) DO NOTHING""",
        values,
        page_size=500,
    )


def load_source_id(cursor: PgCursor, source_code: str = CAPSPACE_SOURCE) -> int:
    cursor.execute("SELECT id FROM data_sources WHERE code=%s", (source_code,))
    row = cursor.fetchone()
    if row is None:
        raise MissingContractSourceError(source_code=source_code)
    return int(row[0])


def count_contract_coverage(
    cursor: PgCursor, first_season: int, last_season: int
) -> dict[str, object]:
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


def load_coverage_report(
    *, first_season: int = DEFAULT_FIRST_SEASON, last_season: int = DEFAULT_LAST_SEASON
) -> dict[str, object]:
    if violation := find_option_violation(
        HistoricalContractOptions(first_season=first_season, last_season=last_season)
    ):
        raise violation
    with (
        open_database_transaction() as connection,
        connection.cursor() as cursor,
    ):
        report = count_contract_coverage(cursor, first_season, last_season)
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
    return report


@runtime_checkable
class ContractRepository(Protocol):
    def select_candidates(
        self, options: HistoricalContractOptions
    ) -> tuple[Candidate, ...]: ...

    def persist_batch(
        self,
        candidates: tuple[Candidate, ...],
        results: tuple[ProfileResult, ...],
        options: HistoricalContractOptions,
        *,
        dry_run: bool,
    ) -> Mapping[str, int]: ...

    def coverage_counts(
        self, options: HistoricalContractOptions
    ) -> Mapping[str, object]: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class PostgresContractRepository:
    cursor: PgCursor

    def select_candidates(
        self, options: HistoricalContractOptions
    ) -> tuple[Candidate, ...]:
        return tuple(
            select_candidates(
                self.cursor,
                first_season=options.first_season,
                last_season=options.last_season,
                limit=options.limit,
                player_id=options.player_id,
                nhl_id=options.nhl_id,
                force=options.force,
            )
        )

    def persist_batch(
        self,
        candidates: tuple[Candidate, ...],
        results: tuple[ProfileResult, ...],
        options: HistoricalContractOptions,
        *,
        dry_run: bool,
    ) -> Mapping[str, int]:
        summary: Counter[str] = Counter()
        source_ids: dict[str, int] = {
            code: load_source_id(self.cursor, code)
            for code in {result.source_code for result in results} | {CAPSPACE_SOURCE}
        }
        if not dry_run:
            for code, records in group_source_records(candidates, results).items():
                save_source_records_bulk(self.cursor, source_ids[code], code, records)
        successful = tuple(
            result for result in results if result.status is ProfileStatus.SUCCEEDED
        )
        if len(successful) == 0:
            return summary
        context = load_persistence_context(
            self.cursor, options.first_season, options.last_season
        )
        for result in successful:
            persist_contracts(
                self.cursor,
                result,
                options,
                source_ids[result.source_code],
                summary,
                preview=dry_run,
                context=context,
            )
        return summary

    def coverage_counts(
        self, options: HistoricalContractOptions
    ) -> Mapping[str, object]:
        return count_contract_coverage(
            self.cursor, options.first_season, options.last_season
        )


type ContractRepositoryFactory = Callable[
    [], AbstractContextManager[ContractRepository]
]


@contextmanager
def open_contract_repository(
    *, context: DiagnosticContext | None = None
) -> Generator[ContractRepository]:
    with (
        open_database_transaction(context=context) as connection,
        connection.cursor() as cursor,
    ):
        yield PostgresContractRepository(cursor=cursor)


@dataclass(slots=True, kw_only=True, frozen=True)
class ContextualContractRepositoryFactory:
    context: DiagnosticContext | None

    def __call__(self) -> AbstractContextManager[ContractRepository]:
        return open_contract_repository(context=self.context)

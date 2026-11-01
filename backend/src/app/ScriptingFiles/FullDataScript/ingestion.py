"""Schema-native ingestion for the TradeValue data sources.

The older scripts in this directory target a retired ORM schema.  This module
loads the same sources directly into ``backend/database/schema.sql`` and keeps
each source stage transactional and repeatable.
"""

import logging
import os
from collections.abc import Mapping
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN
from pathlib import Path
from typing import Iterable

import requests
from app.ScriptingFiles.FullDataScript.source_ingestion.errors import (
    MissingSourceSnapshotError,
    PlayerKindViolation,
)
from app.database import DatabaseTransactionFactory, open_database_transaction, init_db
from app.ScriptingFiles.FullDataScript import capspace
from app.ScriptingFiles.FullDataScript.contracts.active_repository import (
    ContextualActiveRepositoryFactory,
)
from app.ScriptingFiles.FullDataScript.contracts.active_services import (
    ActiveContractService,
)
from app.ScriptingFiles.FullDataScript.contracts.http import (
    ActiveProfileSession,
    ActiveSessionFactory,
    BorrowedActiveSessionFactory,
    SynchronizedActiveSession,
    open_active_session,
)
from app.ScriptingFiles.FullDataScript.contracts.options import (
    ActiveContractOptions,
    find_active_option_violation,
)
from app.ScriptingFiles.FullDataScript.contracts.util import parse_money_cents
from app.ScriptingFiles.FullDataScript.ingestion_tracking import tracked_ingestion
from app.ScriptingFiles.FullDataScript.tracking.domain import IngestionContext
from app.ScriptingFiles.FullDataScript.tracking.services import build_ingestion_context
from app.shared.observability.domain import InvocationContext
from app.shared.cleanup import complete_cleanup
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    DataQualityReport as DataQualityReport,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    PlayerKind,
    serialize_summary,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.errors import (
    IngestionValidationError as IngestionValidationError,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.http import (
    SessionSourceClient,
    SourceClient,
    SourceSession,
    SynchronizedSourceClient,
    open_source_client as open_source_client,
    ContextualSourceClientFactory,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.http import (
    open_http_session as http_session,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.domain import (
    MoneyPuckOptions,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.repository import (
    PostgresMoneyPuckRepository,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.services import (
    MoneyPuckRepository,
    MoneyPuckService,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.domain import (
    NhlRosterOptions,
    NhlStatsOptions,
    StatsJob,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.repository import (
    PostgresNhlRosterRepository,
    PostgresNhlStatsRepository,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.services import (
    NhlRosterRepository,
    NhlRosterService,
    NhlStatsRepository,
    NhlStatsService,
    SourceClientFactory,
    fetch_stats_pages,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.policy import (
    find_quality_violation,
    RowPolicy,
    find_stat_violation,
    validate_rows,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.schedule.domain import (
    ScheduleOptions,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.schedule.repository import (
    PostgresScheduleRepository,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.schedule.services import (
    ScheduleRepository,
    ScheduleService,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.util import (
    parse_season_start_year as _season_start_year,
)

LOGGER = logging.getLogger(__name__)
RECONCILIATION_POLICY = "retain_missing"


def parse_legacy_money_cents(value: object) -> int | None:
    return parse_money_cents(value, rounding=ROUND_HALF_EVEN)


def ingest_capwages(
    session: ActiveProfileSession | None = None,
    *,
    minimum_players: int = 500,
    minimum_profile_success_ratio: float = 0.98,
    context: IngestionContext | None = None,
) -> dict[str, int | str]:
    options = ActiveContractOptions(
        minimum_players=minimum_players,
        minimum_profile_success_ratio=minimum_profile_success_ratio,
    )
    if violation := find_active_option_violation(options):
        raise violation
    return track_active_contracts(session, options, context=context)


@tracked_ingestion("capwages", "ingest_capwages")
def track_active_contracts(
    session: ActiveProfileSession | None,
    options: ActiveContractOptions,
    *,
    context: IngestionContext | None = None,
) -> dict[str, int | str]:
    session_factory: ActiveSessionFactory = open_active_session
    if session is not None:
        session_factory = BorrowedActiveSessionFactory(
            session=SynchronizedActiveSession(session=session)
        )
    return ActiveContractService(
        session_factory=session_factory,
        repository_factory=ContextualActiveRepositoryFactory(context=context),
        context=context,
    ).run(options)


def load_capwages_summary() -> dict[str, int]:
    with open_database_transaction() as connection:
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
    if contracts == 0:
        raise MissingSourceSnapshotError(source="CapWages")
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
    if violation := find_quality_violation(
        report,
        minimum_rows=minimum_rows,
        maximum_duplicate_ratio=maximum_duplicate_ratio,
    ):
        raise violation


def validate_stat_invariants(
    kind: str, row: Mapping[str, object], *, source: str
) -> None:
    try:
        selected = PlayerKind(kind)
    except ValueError as error:
        raise PlayerKindViolation(kind=kind) from error
    if violation := find_stat_violation(selected, row, source=source):
        raise violation


def build_moneypuck_options(
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
    context: IngestionContext | None = None,
) -> dict[str, int | str]:
    options = (
        build_moneypuck_options(
            expected_seasons=expected_seasons,
            minimum_rows_per_kind=minimum_rows_per_kind,
            maximum_duplicate_ratio=maximum_duplicate_ratio,
        )
        if options is None
        else options
    )
    repository = (
        PostgresMoneyPuckRepository(
            transaction=DatabaseTransactionFactory(
                transaction=open_database_transaction, context=context
            )
        )
        if repository is None
        else repository
    )
    return serialize_summary(
        MoneyPuckService(
            client=SessionSourceClient(session=session, context=context),
            repository=repository,
            options=options,
            context=context,
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
    context: IngestionContext | None = None,
) -> dict[str, int | str]:
    repository = (
        PostgresNhlRosterRepository(
            transaction=DatabaseTransactionFactory(
                transaction=open_database_transaction, context=context
            )
        )
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
            client=SessionSourceClient(session=session, context=context),
            repository=repository,
            options=options,
            context=context,
        ).ingest()
    )


def fetch_nhl_stats_pages(
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
    context: IngestionContext | None = None,
) -> dict[str, int | str]:
    options = (
        NhlStatsOptions(first_season=first_season, last_season=last_season)
        if options is None
        else options
    )
    repository = (
        PostgresNhlStatsRepository(
            transaction=DatabaseTransactionFactory(
                transaction=open_database_transaction, context=context
            )
        )
        if repository is None
        else repository
    )
    if client_factory is None:
        client_factory = (
            ContextualSourceClientFactory(context=context)
            if session is None
            else BorrowedSourceClientFactory(
                client=SynchronizedSourceClient(
                    client=SessionSourceClient(session=session, context=context)
                )
            )
        )
    return serialize_summary(
        NhlStatsService(
            client_factory=client_factory,
            repository=repository,
            options=options,
            context=context,
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
    context: IngestionContext | None = None,
) -> dict[str, int | str]:
    repository = (
        PostgresScheduleRepository(
            transaction=DatabaseTransactionFactory(
                transaction=open_database_transaction, context=context
            )
        )
        if repository is None
        else repository
    )
    return serialize_summary(
        ScheduleService(
            client=SessionSourceClient(session=session, context=context),
            repository=repository,
            options=ScheduleOptions(season=season, minimum_games=minimum_games),
            context=context,
        ).ingest()
    )


def run_all(
    *, context: InvocationContext | None = None
) -> dict[str, Mapping[str, object]]:
    init_db()
    session = http_session()
    primary: BaseException | None = None
    try:
        results: dict[str, Mapping[str, object]] = {}
        results["moneypuck"] = ingest_moneypuck(
            session,
            context=build_ingestion_context(
                context, source="moneypuck", stage="ingest_moneypuck"
            ),
        )
        results["nhl_rosters"] = ingest_nhl_rosters(
            session,
            context=build_ingestion_context(
                context, source="nhl", stage="ingest_nhl_rosters"
            ),
        )
        results["nhl_stats"] = ingest_nhl_stats(
            context=build_ingestion_context(
                context, source="nhl", stage="ingest_nhl_stats"
            )
        )
        active_context = build_ingestion_context(
            context, source="capwages", stage="ingest_capwages"
        )
        try:
            results["capwages"] = ingest_capwages(context=active_context)
        except (
            requests.RequestException,
            RuntimeError,
            IngestionValidationError,
        ) as exc:
            results["capwages"] = load_capwages_summary()
            LOGGER.warning(
                "CapWages refresh unavailable; retained last-good database snapshot: %s",
                exc,
                extra=({} if active_context is None else active_context.fields)
                | {"event": "ingestion.snapshot_retained"},
            )
        historical_context = build_ingestion_context(
            context, source="capspace", stage="populate_historical_contracts"
        )
        try:
            results["historical_contracts"] = capspace.ingest_historical_contracts(
                context=historical_context
            )
        except (
            requests.RequestException,
            RuntimeError,
            IngestionValidationError,
        ) as exc:
            results["historical_contracts"] = (
                capspace.load_historical_contract_summary()
            )
            LOGGER.warning(
                "Historical contract refresh unavailable; retained last-good snapshot: %s",
                exc,
                extra=({} if historical_context is None else historical_context.fields)
                | {"event": "ingestion.snapshot_retained"},
            )
        results["schedule"] = ingest_schedule(
            session,
            context=build_ingestion_context(
                context, source="nhl", stage="ingest_schedule"
            ),
        )
        return results
    except BaseException as failure:
        primary = failure
        raise
    finally:
        complete_cleanup((session.close,), primary)


existing_capwages_summary = load_capwages_summary
default_moneypuck_options = build_moneypuck_options


_money_cents = parse_legacy_money_cents
_nhl_stats_pages = fetch_nhl_stats_pages

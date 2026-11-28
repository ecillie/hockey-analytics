"""NHL contract ingestion from CapSpace, queried by NHL player ID.

Two stages share one fetch-and-reconcile path:

- current contracts: every player on a roster this season, refreshed for this
  season and the following ``horizon_years`` on every run;
- historical contracts: played seasons in a range that still have no contract
  season, filled once.

CapWages profiles are kept as an optional fallback for the historical stage,
off by default because capwages.com returns 403 to the ingestion client.
Parsing and money normalisation are deliberately independent of PostgreSQL so
saved source pages can be regression-tested without network access.
"""

import argparse
import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum, auto

from app.database import init_db
from app.ScriptingFiles.FullDataScript.contracts.domain import (
    Candidate as Candidate,
)
from app.ScriptingFiles.FullDataScript.contracts.domain import (
    ContractSeason as ContractSeason,
)
from app.ScriptingFiles.FullDataScript.contracts.domain import (
    ParsedContract as ParsedContract,
)
from app.ScriptingFiles.FullDataScript.contracts.domain import (
    ProfileResult as ProfileResult,
)
from app.ScriptingFiles.FullDataScript.contracts.domain import (
    ProfileSource,
    ProfileStatus,
)
from app.ScriptingFiles.FullDataScript.contracts.errors import (
    CapSpaceError as CapSpaceError,
)
from app.ScriptingFiles.FullDataScript.contracts.errors import (
    CapSpaceParseError as CapSpaceParseError,
)
from app.ScriptingFiles.FullDataScript.contracts.repository.http import (
    BorrowedProfileSessionFactory,
    ProfileSessionFactory,
    SynchronizedProfileSession,
    open_profile_session,
)
from app.ScriptingFiles.FullDataScript.contracts.repository.http import (
    ProfileResponse as ProfileResponse,
)
from app.ScriptingFiles.FullDataScript.contracts.repository.http import (
    ProfileSession as ProfileSession,
)
from app.ScriptingFiles.FullDataScript.contracts.domain import (
    CandidateSelection,
    CurrentContractOptions,
    HistoricalContractOptions,
)
from app.ScriptingFiles.FullDataScript.contracts.errors import (
    ProfileFailureRatioError,
)
from app.ScriptingFiles.FullDataScript.contracts.domain import ProfileHttpOptions
from app.ScriptingFiles.FullDataScript.contracts.policy import find_option_violation
from app.ScriptingFiles.FullDataScript.contracts.repository import (
    ContractRepositoryFactory,
    open_contract_repository as open_contract_repository,
)
from app.ScriptingFiles.FullDataScript.contracts.repository import (
    load_coverage_report as coverage_report,
)
from app.ScriptingFiles.FullDataScript.contracts.repository import (
    load_current_contract_summary as load_current_contract_snapshot,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.errors import (
    MissingSourceSnapshotError,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.util import (
    parse_season_start_year as current_season_start_year,
)
from app.ScriptingFiles.FullDataScript.contracts.repository import (
    select_candidates as select_candidates,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.contracts import (
    normalize_contracts as normalize_contracts,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.contracts import (
    parse_capspace_page as parse_capspace_page,
)
from app.ScriptingFiles.FullDataScript.contracts.services import (
    HistoricalContractService,
    ProfileFetcher,
)
from app.ScriptingFiles.FullDataScript.contracts.util import (
    parse_money_cents,
)
from app.ScriptingFiles.FullDataScript.contracts.util import (
    parse_season_start_year,
)
from app.ScriptingFiles.FullDataScript.ingestion_tracking import tracked_ingestion
from app.ScriptingFiles.FullDataScript.tracking.domain import IngestionContext
from app.ScriptingFiles.FullDataScript.contracts.repository import (
    ContextualContractRepositoryFactory,
)
from app.ScriptingFiles.FullDataScript.tracking.services import build_ingestion_context
from app.config import load_environment
from app.shared.observability.domain import CommandOutcome, read_logging_settings
from app.shared.observability.errors import LoggingSettingsError
from app.shared.observability.services import (
    configure_logging,
    start_command,
    configure_command_exceptions,
    finish_command,
)
from app.shared.cli import ExitCode

CAPSPACE_BASE_URL = ProfileHttpOptions().capspace_base_url
CAPWAGES_BASE_URL = ProfileHttpOptions().capwages_base_url
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
RETRYABLE_HTTP_STATUSES = frozenset(ProfileHttpOptions().retryable_statuses)
CAPWAGES_SLUG_SUFFIXES = ProfileHttpOptions().capwages_slug_suffixes
DEFAULT_FIRST_SEASON = HistoricalContractOptions().first_season
DEFAULT_LAST_SEASON = HistoricalContractOptions().last_season
MAX_WORKERS = HistoricalContractOptions().limits.maximum_workers
DEFAULT_BATCH_SIZE = HistoricalContractOptions().batch_size
MAX_BATCH_SIZE = HistoricalContractOptions().limits.maximum_batch_size


def run_contract_sync(
    session: ProfileSession | None,
    *,
    dry_run: bool,
    first_season: int = DEFAULT_FIRST_SEASON,
    last_season: int = DEFAULT_LAST_SEASON,
    limit: int | None = None,
    workers: int = HistoricalContractOptions().workers,
    batch_size: int = DEFAULT_BATCH_SIZE,
    player_id: int | None = None,
    nhl_id: str | None = None,
    force: bool = False,
    context: IngestionContext | None = None,
) -> dict[str, int]:
    options = HistoricalContractOptions(
        first_season=first_season,
        last_season=last_season,
        limit=limit,
        workers=workers,
        batch_size=batch_size,
        player_id=player_id,
        nhl_id=nhl_id,
        force=force,
    )
    if violation := find_option_violation(options):
        raise violation
    return run_historical_contracts(
        session, options=options, dry_run=dry_run, context=context
    )


def run_historical_contracts(
    session: ProfileSession | None,
    *,
    options: HistoricalContractOptions,
    dry_run: bool,
    repository_factory: ContractRepositoryFactory | None = None,
    context: IngestionContext | None = None,
) -> dict[str, int]:
    if violation := find_option_violation(options):
        raise violation
    session_factory: ProfileSessionFactory = open_profile_session
    if session is not None:
        session_factory = BorrowedProfileSessionFactory(
            session=SynchronizedProfileSession(session=session)
        )
    service = HistoricalContractService(
        repository_factory=ContextualContractRepositoryFactory(context=context)
        if repository_factory is None
        else repository_factory,
        fetcher=ProfileFetcher(session_factory=session_factory, context=context),
        context=context,
    )
    return service.run(options, dry_run=dry_run)


@tracked_ingestion(CAPSPACE_SOURCE, "populate_historical_contracts")
def track_historical_contracts(
    session: ProfileSession | None,
    options: HistoricalContractOptions,
    *,
    context: IngestionContext | None = None,
) -> dict[str, int]:
    return run_historical_contracts(
        session, options=options, dry_run=False, context=context
    )


def ingest_historical_contracts(
    session: ProfileSession | None = None,
    *,
    first_season: int = DEFAULT_FIRST_SEASON,
    last_season: int = DEFAULT_LAST_SEASON,
    limit: int | None = None,
    workers: int = HistoricalContractOptions().workers,
    batch_size: int = DEFAULT_BATCH_SIZE,
    player_id: int | None = None,
    nhl_id: str | None = None,
    force: bool = False,
    context: IngestionContext | None = None,
) -> dict[str, int]:
    options = HistoricalContractOptions(
        first_season=first_season,
        last_season=last_season,
        limit=limit,
        workers=workers,
        batch_size=batch_size,
        player_id=player_id,
        nhl_id=nhl_id,
        force=force,
    )
    if violation := find_option_violation(options):
        raise violation
    return track_historical_contracts(session, options, context=context)


def preview_historical_contracts(
    session: ProfileSession | None = None,
    *,
    first_season: int = DEFAULT_FIRST_SEASON,
    last_season: int = DEFAULT_LAST_SEASON,
    limit: int | None = None,
    workers: int = HistoricalContractOptions().workers,
    batch_size: int = DEFAULT_BATCH_SIZE,
    player_id: int | None = None,
    nhl_id: str | None = None,
    force: bool = False,
    context: IngestionContext | None = None,
) -> dict[str, int]:
    return run_contract_sync(
        session,
        dry_run=True,
        first_season=first_season,
        last_season=last_season,
        limit=limit,
        workers=workers,
        batch_size=batch_size,
        player_id=player_id,
        nhl_id=nhl_id,
        force=force,
        context=context,
    )


def build_current_selection(
    options: CurrentContractOptions,
) -> HistoricalContractOptions:
    return HistoricalContractOptions(
        first_season=options.season,
        last_season=options.season + options.horizon_years,
        workers=options.workers,
        batch_size=options.batch_size,
        selection=CandidateSelection.CURRENT_ROSTER,
    )


def find_profile_failure_violation(
    summary: Mapping[str, int], maximum_ratio: float
) -> ProfileFailureRatioError | None:
    requested = summary.get("profiles_requested", 0)
    failed = summary.get("profiles_failed", 0)
    if requested > 0 and failed / requested > maximum_ratio:
        return ProfileFailureRatioError(
            failed=failed, requested=requested, maximum_ratio=maximum_ratio
        )
    return None


@tracked_ingestion(CAPSPACE_SOURCE, "ingest_current_contracts")
def track_current_contracts(
    session: ProfileSession | None,
    options: CurrentContractOptions,
    *,
    context: IngestionContext | None = None,
) -> dict[str, int]:
    selection = build_current_selection(options)
    if violation := find_option_violation(selection):
        raise violation
    summary = run_historical_contracts(
        session, options=selection, dry_run=False, context=context
    )
    if violation := find_profile_failure_violation(
        summary, options.maximum_profile_failure_ratio
    ):
        raise violation
    return summary


def ingest_current_contracts(
    session: ProfileSession | None = None,
    *,
    season: int | None = None,
    horizon_years: int = CurrentContractOptions(season=0).horizon_years,
    workers: int = CurrentContractOptions(season=0).workers,
    batch_size: int = CurrentContractOptions(season=0).batch_size,
    context: IngestionContext | None = None,
) -> dict[str, int]:
    options = CurrentContractOptions(
        season=current_season_start_year() if season is None else season,
        horizon_years=horizon_years,
        workers=workers,
        batch_size=batch_size,
    )
    return track_current_contracts(session, options, context=context)


def load_current_contract_summary(*, season: int | None = None) -> dict[str, int]:
    resolved = current_season_start_year() if season is None else season
    summary = load_current_contract_snapshot(season=resolved)
    if summary["contracts"] == 0:
        raise MissingSourceSnapshotError(source="CapSpace")
    return summary


def load_historical_contract_summary() -> dict[str, object]:
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


class HistoricalCommandMode(StrEnum):
    PREVIEW = auto()
    APPLY = auto()
    COVERAGE = auto()


@dataclass(slots=True, kw_only=True, frozen=True)
class HistoricalCommandOptions:
    ingestion: HistoricalContractOptions
    mode: HistoricalCommandMode = HistoricalCommandMode.PREVIEW


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    defaults = HistoricalContractOptions()
    parser = argparse.ArgumentParser(
        description="Gap-fill historical NHL contracts from CapSpace and CapWages"
    )
    mode = parser.add_mutually_exclusive_group()
    parser.set_defaults(mode=HistoricalCommandMode.PREVIEW)
    mode.add_argument(
        "--dry-run",
        action="store_const",
        dest="mode",
        const=HistoricalCommandMode.PREVIEW,
        help="preview without contract/source-record mutations",
    )
    mode.add_argument(
        "--apply",
        action="store_const",
        dest="mode",
        const=HistoricalCommandMode.APPLY,
        help="persist the backfill",
    )
    mode.add_argument(
        "--coverage",
        action="store_const",
        dest="mode",
        const=HistoricalCommandMode.COVERAGE,
        help="print current historical contract coverage and exit",
    )
    parser.add_argument("--nhl-id")
    parser.add_argument("--player-id", type=int)
    parser.add_argument("--first-season", type=int, default=defaults.first_season)
    parser.add_argument("--last-season", type=int, default=defaults.last_season)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=defaults.workers)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=defaults.batch_size,
        help=f"players fetched and committed per batch (1-{defaults.limits.maximum_batch_size})",
    )
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    options = HistoricalCommandOptions(
        ingestion=HistoricalContractOptions(
            first_season=args.first_season,
            last_season=args.last_season,
            limit=args.limit,
            workers=args.workers,
            batch_size=args.batch_size,
            player_id=args.player_id,
            nhl_id=args.nhl_id,
            force=args.force,
        ),
        mode=args.mode,
    )
    if violation := find_option_violation(options.ingestion):
        parser.error(str(violation))
    try:
        settings = read_logging_settings(load_environment())
    except LoggingSettingsError as error:
        parser.error(str(error))
    configure_logging(settings)
    context = start_command("historical_contracts")
    configure_command_exceptions(context)
    try:
        summary = execute_historical_command(
            options,
            context=build_ingestion_context(
                context, source="capspace", stage="populate_historical_contracts"
            ),
        )
    except Exception:
        logger.exception(
            "Historical contract command failed",
            extra=context.fields | {"event": "command.failed"},
        )
        finish_command(context, CommandOutcome.FAILED)
        return ExitCode.FAILURE
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    finish_command(context, CommandOutcome.COMPLETED)
    return ExitCode.SUCCESS


def execute_historical_command(
    options: HistoricalCommandOptions,
    *,
    context: IngestionContext | None = None,
) -> Mapping[str, object]:
    init_db()
    if options.mode is HistoricalCommandMode.COVERAGE:
        return coverage_report(
            first_season=options.ingestion.first_season,
            last_season=options.ingestion.last_season,
        )
    if options.mode is HistoricalCommandMode.APPLY:
        return track_historical_contracts(None, options.ingestion, context=context)
    return run_historical_contracts(
        None, options=options.ingestion, dry_run=True, context=context
    )


existing_historical_contract_summary = load_historical_contract_summary
money_to_cents = parse_money_cents
season_start_year = parse_season_start_year

if __name__ == "__main__":
    raise SystemExit(main())

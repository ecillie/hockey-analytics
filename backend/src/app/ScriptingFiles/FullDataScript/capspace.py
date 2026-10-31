"""Gap-driven historical NHL contract ingestion from CapSpace and CapWages.

The normal CapWages refresh starts from its active-player index. This module
fills the resulting historical gaps by selecting players from NHL stats and
querying CapSpace directly by NHL ID, then trying identity-validated CapWages
profiles when CapSpace cannot cover a requested season. Parsing and money
normalisation are deliberately independent of PostgreSQL so saved source pages
can be regression-tested without network access.
"""

import argparse
import json

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
from app.ScriptingFiles.FullDataScript.contracts.http import (
    BorrowedProfileSessionFactory,
    ProfileSessionFactory,
    SynchronizedProfileSession,
    open_profile_session,
)
from app.ScriptingFiles.FullDataScript.contracts.http import (
    ProfileResponse as ProfileResponse,
)
from app.ScriptingFiles.FullDataScript.contracts.http import (
    ProfileSession as ProfileSession,
)
from app.ScriptingFiles.FullDataScript.contracts.options import (
    HistoricalContractOptions,
    find_option_violation,
)
from app.ScriptingFiles.FullDataScript.contracts.repository import (
    ContractRepositoryFactory,
    open_contract_repository,
)
from app.ScriptingFiles.FullDataScript.contracts.repository import (
    coverage_report as coverage_report,
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
    money_to_cents as money_to_cents,
)
from app.ScriptingFiles.FullDataScript.contracts.util import (
    season_start_year as season_start_year,
)
from app.ScriptingFiles.FullDataScript.ingestion_tracking import tracked_ingestion

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


def _run(
    session: ProfileSession | None,
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
    return run_historical_contracts(session, options=options, dry_run=dry_run)


def run_historical_contracts(
    session: ProfileSession | None,
    *,
    options: HistoricalContractOptions,
    dry_run: bool,
    repository_factory: ContractRepositoryFactory = open_contract_repository,
) -> dict[str, int]:
    if violation := find_option_violation(options):
        raise violation
    session_factory: ProfileSessionFactory = open_profile_session
    if session is not None:
        session_factory = BorrowedProfileSessionFactory(
            session=SynchronizedProfileSession(session=session)
        )
    service = HistoricalContractService(
        repository_factory=repository_factory,
        fetcher=ProfileFetcher(session_factory=session_factory),
    )
    return service.run(options, dry_run=dry_run)


@tracked_ingestion(CAPSPACE_SOURCE, "populate_historical_contracts")
def track_historical_contracts(
    session: ProfileSession | None, options: HistoricalContractOptions
) -> dict[str, int]:
    return run_historical_contracts(session, options=options, dry_run=False)


def ingest_historical_contracts(
    session: ProfileSession | None = None,
    *,
    first_season: int = DEFAULT_FIRST_SEASON,
    last_season: int = DEFAULT_LAST_SEASON,
    limit: int | None = None,
    workers: int = 4,
    batch_size: int = DEFAULT_BATCH_SIZE,
    player_id: int | None = None,
    nhl_id: str | None = None,
    force: bool = False,
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
    return track_historical_contracts(session, options)


def preview_historical_contracts(
    session: ProfileSession | None = None,
    *,
    first_season: int = DEFAULT_FIRST_SEASON,
    last_season: int = DEFAULT_LAST_SEASON,
    limit: int | None = None,
    workers: int = 4,
    batch_size: int = DEFAULT_BATCH_SIZE,
    player_id: int | None = None,
    nhl_id: str | None = None,
    force: bool = False,
) -> dict[str, int]:
    return _run(
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
    )


def existing_historical_contract_summary() -> dict[str, object]:
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
    selected_options = HistoricalContractOptions(
        first_season=args.first_season,
        last_season=args.last_season,
        limit=args.limit,
        workers=args.workers,
        batch_size=args.batch_size,
        player_id=args.player_id,
        nhl_id=args.nhl_id,
        force=args.force,
    )
    if violation := find_option_violation(selected_options):
        parser.error(str(violation))
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
    summary = (
        track_historical_contracts(None, selected_options)
        if args.apply
        else run_historical_contracts(None, options=selected_options, dry_run=True)
    )
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

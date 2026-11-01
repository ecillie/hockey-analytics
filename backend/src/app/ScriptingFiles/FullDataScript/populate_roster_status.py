"""Populate player roster statuses from the free NHL/AHL roster feeds.

Usage from the repository root:
    uv run python -m app.ScriptingFiles.FullDataScript.populate_roster_status
"""

import argparse
import json
import logging
import os
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date

from app.database import open_database_transaction, init_db
from app.ScriptingFiles.FullDataScript.ingestion_tracking import tracked_ingestion
from app.ScriptingFiles.FullDataScript.roster_status.ahl_roster_service import (
    AhlRosterService,
)
from app.ScriptingFiles.FullDataScript.roster_status.domain import AhlFeedOptions
from app.ScriptingFiles.FullDataScript.roster_status.errors import (
    IncompleteRosterFeedError,
)
from app.ScriptingFiles.FullDataScript.roster_status.http_json_client import (
    JsonHttpClient,
)
from app.ScriptingFiles.FullDataScript.roster_status.nhl_roster_service import (
    NhlRosterService,
)
from app.ScriptingFiles.FullDataScript.roster_status.repository import (
    PostgresRosterRepository,
)
from app.ScriptingFiles.FullDataScript.roster_status.services import (
    RosterFeed,
    RosterStatusService,
)
from app.shared.cli import ExitCode
from app.config import load_environment
from app.shared.observability.domain import CommandOutcome, read_logging_settings
from app.shared.observability.errors import LoggingSettingsError
from app.shared.observability.services import (
    configure_logging,
    start_command,
    configure_command_exceptions,
    finish_command,
)
from app.ScriptingFiles.FullDataScript.tracking.domain import IngestionContext
from app.ScriptingFiles.FullDataScript.tracking.services import build_ingestion_context

logger = logging.getLogger(__name__)


@tracked_ingestion("nhl", "populate_roster_status")
def sync_roster_status(
    *,
    nhl_service: RosterFeed | None = None,
    ahl_service: RosterFeed | None = None,
    as_of: date | None = None,
    context: IngestionContext | None = None,
) -> dict[str, object]:
    nhl_service = (
        NhlRosterService(http_client=JsonHttpClient())
        if nhl_service is None
        else nhl_service
    )
    if ahl_service is None:
        options = AhlFeedOptions(
            feed_key=os.environ.get("AHL_FEED_KEY", AhlFeedOptions().feed_key),
            season_id=os.environ.get("AHL_SEASON_ID"),
        )
        ahl_service = AhlRosterService(http_client=JsonHttpClient(), options=options)
    with open_database_transaction(context=context) as connection:
        service = RosterStatusService(
            repository=PostgresRosterRepository(connection=connection),
            nhl_service=nhl_service,
            ahl_service=ahl_service,
            context=context,
        )
        summary = service.sync(as_of)
        if not summary.nhl_complete or not summary.ahl_complete:
            raise IncompleteRosterFeedError(errors=summary.errors)
        result = asdict(summary)
        result.update(
            {
                "records_read": summary.statuses_updated + summary.preserved_count,
                "records_updated": summary.statuses_updated,
                "records_skipped": summary.preserved_count,
            }
        )
        return result


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    try:
        settings = read_logging_settings(load_environment())
    except LoggingSettingsError as error:
        parser.error(str(error))
    configure_logging(settings)
    context = start_command("roster_status")
    configure_command_exceptions(context)
    try:
        init_db()
        summary = sync_roster_status(
            context=build_ingestion_context(
                context, source="nhl", stage="populate_roster_status"
            )
        )
    except Exception as error:
        incomplete = isinstance(error, IncompleteRosterFeedError)
        logger.exception(
            "Roster-status sync refused an incomplete feed; changes were rolled back"
            if incomplete
            else "Roster-status sync failed; database changes were rolled back",
            extra=context.fields | {"event": "command.failed"},
        )
        finish_command(
            context, CommandOutcome.INCOMPLETE if incomplete else CommandOutcome.FAILED
        )
        return ExitCode.INCOMPLETE if incomplete else ExitCode.FAILURE

    logger.info(
        "Roster sync complete: updated=%s active=%s minors=%s ltir=%s "
        "unknown=%s preserved=%s",
        summary["statuses_updated"],
        summary["active_count"],
        summary["minors_count"],
        summary["ltir_count"],
        summary["unknown_count"],
        summary["preserved_count"],
        extra=context.fields
        | {
            "event": "ingestion.roster_completed",
            "committed": summary["statuses_updated"],
        },
    )
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    finish_command(context, CommandOutcome.COMPLETED)
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())

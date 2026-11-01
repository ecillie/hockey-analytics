"""Run the complete schema-native ingestion pipeline."""

import argparse
import json
import logging
from collections.abc import Sequence

from app.database import init_db
from app.ScriptingFiles.FullDataScript.ingestion import run_all
from app.ScriptingFiles.FullDataScript.populate_roster_status import (
    sync_roster_status,
)
from app.ScriptingFiles.FullDataScript.roster_status.errors import (
    IncompleteRosterFeedError,
)
from app.shared.cli import ExitCode
from app.config import load_environment
from app.shared.observability.domain import CommandOutcome, read_logging_settings
from app.shared.observability.errors import LoggingSettingsError
from app.shared.observability.services import (
    configure_logging,
    start_command,
    finish_command,
)
from app.ScriptingFiles.FullDataScript.tracking.services import build_ingestion_context

logger = logging.getLogger(__name__)


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
    context = start_command("ingestion")
    try:
        summary = run_all(context=context)
        init_db()
        sync_roster_status(
            context=build_ingestion_context(
                context, source="nhl", stage="populate_roster_status"
            )
        )
    except Exception as error:
        incomplete = isinstance(error, IncompleteRosterFeedError)
        logger.exception(
            "Ingestion refused an incomplete roster feed"
            if incomplete
            else "Ingestion failed",
            extra=context.fields | {"event": "command.failed"},
        )
        finish_command(
            context, CommandOutcome.INCOMPLETE if incomplete else CommandOutcome.FAILED
        )
        return ExitCode.INCOMPLETE if incomplete else ExitCode.FAILURE

    print(json.dumps(summary, indent=2, sort_keys=True))
    finish_command(context, CommandOutcome.COMPLETED)
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())

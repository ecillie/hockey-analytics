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
from app.shared.observability.domain import (
    CommandOutcome,
    read_logging_settings,
    read_telemetry_settings,
)
from app.shared.observability.errors import (
    LoggingSettingsError,
    TelemetrySettingsError,
)
from app.shared.observability.services import (
    configure_logging,
    start_command,
    configure_command_exceptions,
    finish_command,
)
from app.shared.observability.telemetry import configure_telemetry
from app.ScriptingFiles.FullDataScript.tracking.services import build_ingestion_context

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    environment = load_environment()
    try:
        settings = read_logging_settings(environment)
        telemetry_settings = read_telemetry_settings(environment)
    except (LoggingSettingsError, TelemetrySettingsError) as error:
        parser.error(str(error))
    configure_logging(settings)
    # stderr delivery is off in nonprod and prod, so Application Insights is the
    # only place a deployed run's logs land. Shut it down to flush the last batch.
    telemetry = configure_telemetry(
        settings, telemetry_settings, service_name="tradevalue-ingestion"
    )
    try:
        return run_ingestion()
    finally:
        if telemetry is not None:
            telemetry.shutdown()


def run_ingestion() -> int:
    context = start_command("ingestion")
    configure_command_exceptions(context)
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

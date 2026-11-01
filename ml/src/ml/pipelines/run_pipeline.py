"""Dataset pipeline command with frozen CLI options."""

import argparse
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from app.config import load_environment
from app.shared.cli import CommandOptionError, ExitCode
from app.shared.observability.domain import CommandOutcome, read_logging_settings
from app.shared.observability.errors import LoggingSettingsError
from ml.observability.services import report_ml_progress
from app.shared.observability.services import (
    configure_logging,
    start_command,
    configure_command_exceptions,
    finish_command,
)

from ml.pipelines.build_model_dataset import (
    print_model_dataset_diagnostics,
)
from ml.pipelines.services import run_pipeline


@dataclass(slots=True, kw_only=True, frozen=True)
class PipelineOptions:
    min_games: int = 1


logger = logging.getLogger(__name__)


def find_option_violation(options: PipelineOptions) -> CommandOptionError | None:
    if options.min_games < 1:
        return CommandOptionError(option="min-games", requirement="must be positive")
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Build the Hockey Analytics skater ML dataset.")
    )

    parser.add_argument(
        "--min-games",
        type=int,
        default=1,
        help=("Minimum games played required for a player-season."),
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    options = PipelineOptions(**vars(parser.parse_args(argv)))
    if violation := find_option_violation(options):
        parser.error(str(violation))
    try:
        settings = read_logging_settings(load_environment())
    except LoggingSettingsError as error:
        parser.error(str(error))
    configure_logging(settings)
    context = start_command("ml.run_pipeline")
    configure_command_exceptions(context)
    try:
        dataset = run_pipeline(min_games=options.min_games)
        report_ml_progress(
            context,
            event="ml.dataset_ready",
            stage="pipeline",
            values={"rows": len(dataset)},
        )
        print_model_dataset_diagnostics(dataset)
    except Exception:
        logger.exception(
            "ML dataset pipeline failed",
            extra=context.fields | {"event": "command.failed"},
        )
        finish_command(context, CommandOutcome.FAILED)
        return ExitCode.FAILURE
    finish_command(context, CommandOutcome.COMPLETED)
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())

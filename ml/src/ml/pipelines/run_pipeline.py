import argparse
import logging
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd
from app.config import get_database_settings, load_environment
from app.database import open_database_resources
from app.shared.cli import CommandOptionError, ExitCode
from app.shared.observability.domain import CommandOutcome, read_logging_settings
from app.shared.observability.errors import LoggingSettingsError
from ml.observability.services import report_ml_progress
from app.shared.observability.services import (
    configure_logging,
    start_command,
    finish_command,
)

from ml.pipelines.build_model_dataset import (
    build_model_dataset,
    print_model_dataset_diagnostics,
)
from ml.pipelines.load_player_stats import load_player_stats
from ml.pipelines.load_salary_cap import load_salary_cap
from ml.errors import MinimumGamesError


def run_pipeline(
    min_games: int = 1,
    *,
    players: pd.DataFrame | None = None,
    salary_caps: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if min_games < 1:
        raise MinimumGamesError(field="min_games", value=min_games)
    if players is None or salary_caps is None:
        with (
            open_database_resources(get_database_settings()) as resources,
            resources.engine.connect() as connection,
        ):
            if players is None:
                players = load_player_stats(min_games=min_games, connection=connection)
            if salary_caps is None:
                salary_caps = load_salary_cap(connection=connection)
    return build_model_dataset(
        min_games=min_games, players=players, salary_cap=salary_caps
    )


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

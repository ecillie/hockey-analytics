import argparse
import logging
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd
from app.config import get_database_settings
from app.database import database_resources
from app.shared.cli import CommandOptionError, ExitCode

from ml.pipelines.build_model_dataset import (
    build_model_dataset,
    print_model_dataset_diagnostics,
)
from ml.pipelines.load_player_stats import load_player_stats
from ml.pipelines.load_salary_cap import load_salary_cap


def run_pipeline(
    min_games: int = 1,
    *,
    players: pd.DataFrame | None = None,
    salary_caps: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if min_games < 1:
        raise ValueError("min_games must be positive")
    if players is None or salary_caps is None:
        with (
            database_resources(get_database_settings()) as resources,
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
    logging.basicConfig(level=logging.INFO)
    try:
        print_model_dataset_diagnostics(run_pipeline(min_games=options.min_games))
    except Exception:
        logger.exception("ML dataset pipeline failed")
        return ExitCode.FAILURE
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())

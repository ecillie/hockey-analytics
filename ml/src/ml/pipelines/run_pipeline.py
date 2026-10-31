import argparse

import pandas as pd
from app.config import get_database_settings
from app.database import database_resources

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description=("Build the Hockey Analytics skater ML dataset.")
    )

    parser.add_argument(
        "--min-games",
        type=int,
        default=1,
        help=("Minimum games played required for a player-season."),
    )

    args = parser.parse_args()

    print_model_dataset_diagnostics(run_pipeline(min_games=args.min_games))


if __name__ == "__main__":
    main()

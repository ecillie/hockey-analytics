import argparse
import logging
from collections.abc import Sequence

import pandas as pd
from app.shared.cli import ExitCode
from app.config import load_environment
from app.shared.observability.domain import CommandOutcome, read_logging_settings
from app.shared.observability.errors import LoggingSettingsError
from ml.observability.services import report_ml_progress
from app.shared.observability.services import (
    configure_logging,
    start_command,
    configure_command_exceptions,
    finish_command,
)

from ml.errors import MinimumGamesError, ContractLeakageError, FrameGrainError
from ml.configuration import FeatureOptions
from ml.pipelines.load_player_stats import load_player_stats
from ml.pipelines.load_salary_cap import load_salary_cap
from ml.schemas import validate_feature_options, validate_frame

FORBIDDEN_CONTRACT_COLUMNS = frozenset(
    {
        "contract_id",
        "contract_type",
        "average_value_cents",
        "cap_hit_cents",
        "cap_percentage",
        "actual_cap_hit",
        "aav",
    }
)


def build_model_dataset(
    min_games: int = 1,
    *,
    players: pd.DataFrame | None = None,
    salary_cap: pd.DataFrame | None = None,
    options: FeatureOptions | None = None,
) -> pd.DataFrame:

    selected = options or FeatureOptions()
    validate_feature_options(selected)
    if min_games < 1:
        raise MinimumGamesError(field="min_games", value=min_games)
    if players is None:
        players = load_player_stats(min_games=min_games)
    if salary_cap is None:
        salary_cap = load_salary_cap()
    validate_frame(
        players,
        required=("player_id", "season", "position", "games_played"),
        grain=("player_id", "season"),
    )
    validate_frame(
        salary_cap,
        required=("season", "season_label", "salary_cap_cents", "salary_cap_dollars"),
        grain=("season",),
    )
    players = players.loc[players["games_played"].fillna(0) >= min_games].copy()

    df = players.merge(
        salary_cap[
            [
                "season",
                "season_label",
                "salary_cap_cents",
                "salary_cap_dollars",
            ]
        ],
        how="left",
        on="season",
        validate="many_to_one",
    )

    df["position_group"] = df["position"].map(
        {
            "C": "forward",
            "LW": "forward",
            "RW": "forward",
            "F": "forward",
            "D": "defense",
        }
    )
    df["salary_cap_fraction"] = (
        df["salary_cap_dollars"] / selected.salary_cap_normalization_dollars
    )

    duplicate_count = df.duplicated(subset=["player_id", "season"]).sum()

    if duplicate_count:
        raise FrameGrainError(grain=("player_id", "season"))

    leaked_columns = FORBIDDEN_CONTRACT_COLUMNS.intersection(df.columns)

    if leaked_columns:
        raise ContractLeakageError(columns=tuple(sorted(leaked_columns)))

    return df.reset_index(drop=True)


def print_model_dataset_diagnostics(
    df: pd.DataFrame,
) -> None:
    print("\n=== MODEL DATASET ===")
    print(f"Rows: {len(df):,}")

    if df.empty:
        print("No model rows found.")
        return

    print(f"Players: {df['player_id'].nunique():,}")

    print(f"Seasons: {df['season'].min()} - {df['season'].max()}")

    print(f"Columns: {len(df.columns)}")

    duplicates = df.duplicated(["player_id", "season"]).sum()

    print(f"Duplicate player-seasons: {duplicates:,}")

    advanced_count = df["ice_time_seconds"].notna().sum()

    salary_cap_count = df["salary_cap_cents"].notna().sum()

    print(f"Advanced stats coverage: {advanced_count:,} / {len(df):,}")

    print(f"Salary cap coverage: {salary_cap_count:,} / {len(df):,}")

    print("\nRows by position group:")

    print(df["position_group"].value_counts(dropna=False).to_string())

    print("\nRows by season:")

    print(df.groupby("season").size().sort_index().to_string())

    sample_columns = [
        "player_name",
        "season",
        "position",
        "games_played",
        "goals",
        "assists",
        "points",
        "individual_expected_goals",
        "on_ice_expected_goals_pct",
        "game_score",
        "salary_cap_dollars",
    ]

    print("\nSample:")

    print(df[sample_columns].head(15).to_string(index=False))


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="build model dataset")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    try:
        settings = read_logging_settings(load_environment())
    except LoggingSettingsError as error:
        parser.error(str(error))
    configure_logging(settings)
    context = start_command("ml.build_model_dataset")
    configure_command_exceptions(context)
    try:
        dataset = build_model_dataset()
        report_ml_progress(
            context,
            event="ml.dataset_ready",
            stage="model_dataset",
            values={"rows": len(dataset)},
        )
        print_model_dataset_diagnostics(dataset)
    except Exception:
        logger.exception(
            "Command failed", extra=context.fields | {"event": "command.failed"}
        )
        finish_command(context, CommandOutcome.FAILED)
        return ExitCode.FAILURE
    finish_command(context, CommandOutcome.COMPLETED)
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())

"""Model-dataset command and stdout report compatibility boundary."""

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

from ml.pipelines.services import (
    build_model_dataset,
    FORBIDDEN_CONTRACT_COLUMNS as FORBIDDEN_CONTRACT_COLUMNS,
)


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

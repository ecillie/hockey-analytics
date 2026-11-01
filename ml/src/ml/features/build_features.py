"""Feature-building command and stdout report compatibility boundary."""

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

from ml.domain import MODEL_FEATURE_COLUMNS
from ml.features.services import (
    build_features,
    get_training_dataset as get_training_dataset,
)
from ml.features.util import calculate_per_60 as calculate_per_60


def print_feature_diagnostics(
    df: pd.DataFrame,
) -> None:
    print("\n=== SKATER FEATURES ===")
    print(f"Rows: {len(df):,}")

    if df.empty:
        print("No feature rows found.")
        return

    eligible = int(df["eligible_for_training"].sum())

    print(f"Training-eligible rows: {eligible:,} / {len(df):,}")

    print(f"Feature columns: {len(MODEL_FEATURE_COLUMNS)}")

    print("\nMissing values by model feature:")

    missing = df[list(MODEL_FEATURE_COLUMNS)].isna().sum().sort_values(ascending=False)

    print(missing.to_string())

    print("\nSample:")

    sample_columns = [
        "player_name",
        "season",
        "position",
        "games_played",
        "toi_hours",
        "goals_per_60",
        "assists_per_60",
        "points_per_60",
        "xg_per_60",
        "game_score_per_60",
        "on_ice_expected_goals_pct",
        "eligible_for_training",
    ]

    print(df[sample_columns].head(15).to_string(index=False))


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="build features")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    try:
        settings = read_logging_settings(load_environment())
    except LoggingSettingsError as error:
        parser.error(str(error))
    configure_logging(settings)
    context = start_command("ml.build_features")
    configure_command_exceptions(context)
    try:
        feature_data = build_features()
        report_ml_progress(
            context,
            event="ml.dataset_ready",
            stage="features",
            values={"rows": len(feature_data)},
        )
        print_feature_diagnostics(feature_data)
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

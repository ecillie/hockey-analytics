import argparse
import logging
from collections.abc import Sequence

import numpy as np
import pandas as pd
from app.shared.cli import ExitCode
from app.config import load_environment
from app.shared.observability.domain import CommandOutcome, read_logging_settings
from app.shared.observability.errors import LoggingSettingsError
from ml.observability.services import report_ml_progress
from app.shared.observability.services import (
    configure_logging,
    start_command,
    finish_command,
)

from ml.configuration import MODEL_FEATURE_COLUMNS, FeatureOptions
from ml.pipelines.build_model_dataset import build_model_dataset
from ml.schemas import validate_feature_options, validate_frame


def calculate_per_60(
    values: pd.Series,
    ice_time_seconds: pd.Series,
) -> pd.Series:
    valid_toi = ice_time_seconds.where(ice_time_seconds > 0)

    return values.astype(float) * 3600.0 / valid_toi


def build_features(
    df: pd.DataFrame | None = None,
    *,
    options: FeatureOptions | None = None,
) -> pd.DataFrame:

    selected = options or FeatureOptions()
    validate_feature_options(selected)
    if df is None:
        df = build_model_dataset(options=selected)
    validate_frame(
        df,
        required=(
            "player_id",
            "season",
            "games_played",
            "ice_time_seconds",
            "goals",
            "assists",
            "points",
            "individual_expected_goals",
            "individual_shots_on_goal",
            "individual_unblocked_attempts",
            "game_score",
            "individual_primary_assists",
            "individual_secondary_assists",
            "takeaways",
            "giveaways",
            "shots_blocked",
            "penalties",
            "penalties_drawn",
            "offensive_zone_shift_starts",
            "defensive_zone_shift_starts",
            "neutral_zone_shift_starts",
            "on_ice_expected_goals_pct",
        ),
        grain=("player_id", "season"),
    )
    features = df.copy()

    if "position_group" not in features.columns and "position" in features.columns:
        features["position_group"] = features["position"].map(
            {
                "C": "forward",
                "LW": "forward",
                "RW": "forward",
                "F": "forward",
                "D": "defense",
            }
        )

    features["toi_minutes"] = features["ice_time_seconds"] / 60.0

    features["toi_hours"] = features["ice_time_seconds"] / 3600.0

    features["goals_per_60"] = calculate_per_60(
        features["goals"],
        features["ice_time_seconds"],
    )

    features["assists_per_60"] = calculate_per_60(
        features["assists"],
        features["ice_time_seconds"],
    )

    features["points_per_60"] = calculate_per_60(
        features["points"],
        features["ice_time_seconds"],
    )

    features["xg_per_60"] = calculate_per_60(
        features["individual_expected_goals"],
        features["ice_time_seconds"],
    )

    features["shots_on_goal_per_60"] = calculate_per_60(
        features["individual_shots_on_goal"],
        features["ice_time_seconds"],
    )

    features["unblocked_attempts_per_60"] = calculate_per_60(
        features["individual_unblocked_attempts"],
        features["ice_time_seconds"],
    )

    features["game_score_per_60"] = calculate_per_60(
        features["game_score"],
        features["ice_time_seconds"],
    )

    features["primary_assists_per_60"] = calculate_per_60(
        features["individual_primary_assists"],
        features["ice_time_seconds"],
    )

    features["secondary_assists_per_60"] = calculate_per_60(
        features["individual_secondary_assists"],
        features["ice_time_seconds"],
    )

    features["takeaways_per_60"] = calculate_per_60(
        features["takeaways"],
        features["ice_time_seconds"],
    )

    features["giveaways_per_60"] = calculate_per_60(
        features["giveaways"],
        features["ice_time_seconds"],
    )

    features["net_takeaways_per_60"] = (
        features["takeaways_per_60"] - features["giveaways_per_60"]
    )

    features["blocks_per_60"] = calculate_per_60(
        features["shots_blocked"],
        features["ice_time_seconds"],
    )

    features["penalties_per_60"] = calculate_per_60(
        features["penalties"],
        features["ice_time_seconds"],
    )

    features["penalties_drawn_per_60"] = calculate_per_60(
        features["penalties_drawn"],
        features["ice_time_seconds"],
    )

    features["penalty_differential_per_60"] = (
        features["penalties_drawn_per_60"] - features["penalties_per_60"]
    )

    features["goals_above_expected"] = (
        features["goals"] - features["individual_expected_goals"]
    )

    features["goals_above_expected_per_60"] = calculate_per_60(
        features["goals_above_expected"],
        features["ice_time_seconds"],
    )

    zone_start_total = (
        features["offensive_zone_shift_starts"].fillna(0)
        + features["defensive_zone_shift_starts"].fillna(0)
        + features["neutral_zone_shift_starts"].fillna(0)
    )

    valid_zone_starts = zone_start_total.where(zone_start_total > 0)

    features["offensive_zone_start_pct"] = (
        features["offensive_zone_shift_starts"] / valid_zone_starts
    )

    features["defensive_zone_start_pct"] = (
        features["defensive_zone_shift_starts"] / valid_zone_starts
    )

    features["neutral_zone_start_pct"] = (
        features["neutral_zone_shift_starts"] / valid_zone_starts
    )

    features["eligible_for_training"] = (
        features["games_played"].fillna(0) >= selected.minimum_training_games
    ) & (features["ice_time_seconds"].fillna(0) > 0)

    features.replace(
        [np.inf, -np.inf],
        np.nan,
        inplace=True,
    )

    return features.reset_index(drop=True)


def get_training_dataset(
    df: pd.DataFrame | None = None,
    *,
    options: FeatureOptions | None = None,
) -> pd.DataFrame:

    features = build_features(df, options=options)

    return features[features["eligible_for_training"]].reset_index(drop=True)


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

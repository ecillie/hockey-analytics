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
    finish_command,
)

from ml.errors import ReplacementPercentileError
from ml.configuration import HIGHER_IS_BETTER, LOWER_IS_BETTER, FeatureOptions
from ml.features.build_features import build_features

REPLACEMENT_FEATURES = HIGHER_IS_BETTER + LOWER_IS_BETTER


def calculate_replacement_level(
    df: pd.DataFrame | None = None,
    replacement_percentile: float | None = None,
    *,
    options: FeatureOptions | None = None,
) -> pd.DataFrame:

    selected = options or FeatureOptions()
    percentile = (
        selected.replacement_percentile
        if replacement_percentile is None
        else replacement_percentile
    )
    if not 0 <= percentile <= 1:
        raise ReplacementPercentileError(value=percentile)
    result = build_features(df, options=selected)

    valid_games = result["games_played"].where(result["games_played"] > 0)

    result["toi_per_game"] = result["toi_minutes"] / valid_games

    eligible = result[
        result["eligible_for_training"]
        & result["position_group"].notna()
        & result["toi_per_game"].notna()
    ].copy()

    thresholds = (
        eligible.groupby(["season", "position_group"])["toi_per_game"]
        .quantile(percentile)
        .rename("replacement_toi_per_game_threshold")
        .reset_index()
    )

    eligible = eligible.merge(
        thresholds,
        on=["season", "position_group"],
        how="left",
        validate="many_to_one",
    )

    replacement_pool = eligible[
        eligible["toi_per_game"] <= eligible["replacement_toi_per_game_threshold"]
    ].copy()

    baselines = (
        replacement_pool.groupby(["season", "position_group"])[
            list(REPLACEMENT_FEATURES)
        ]
        .median()
        .reset_index()
    )

    baselines = baselines.rename(
        columns={feature: f"replacement_{feature}" for feature in REPLACEMENT_FEATURES}
    )

    result = result.merge(
        thresholds,
        on=["season", "position_group"],
        how="left",
        validate="many_to_one",
    )

    result = result.merge(
        baselines,
        on=["season", "position_group"],
        how="left",
        validate="many_to_one",
    )

    replacement_keys = set(
        zip(
            replacement_pool["player_id"],
            replacement_pool["season"],
        )
    )

    result["is_replacement_pool"] = [
        (player_id, season) in replacement_keys
        for player_id, season in zip(
            result["player_id"],
            result["season"],
        )
    ]

    for feature in HIGHER_IS_BETTER:
        result[f"{feature}_above_replacement"] = (
            result[feature] - result[f"replacement_{feature}"]
        )

    for feature in LOWER_IS_BETTER:
        result[f"{feature}_above_replacement"] = (
            result[f"replacement_{feature}"] - result[feature]
        )

    result = result.reset_index(drop=True)
    result.attrs["replacement_percentile"] = percentile
    return result


def print_replacement_diagnostics(
    df: pd.DataFrame,
) -> None:
    print("\n=== REPLACEMENT LEVEL ===")

    print(f"Player-season rows: {len(df):,}")

    replacement_count = int(df["is_replacement_pool"].sum())

    print(f"Replacement-pool rows: {replacement_count:,}")

    percentile = df.attrs.get(
        "replacement_percentile", FeatureOptions().replacement_percentile
    )
    print(f"Replacement percentile: {percentile:.0%}")

    print("\nReplacement players by position:")

    print(
        df.loc[
            df["is_replacement_pool"],
            "position_group",
        ]
        .value_counts()
        .to_string()
    )

    print("\nReplacement TOI thresholds:")

    thresholds = (
        df[
            [
                "season",
                "position_group",
                "replacement_toi_per_game_threshold",
            ]
        ]
        .drop_duplicates()
        .sort_values(["season", "position_group"])
    )

    print(thresholds.tail(12).to_string(index=False))

    print("\nSample above-replacement values:")

    sample_columns = [
        "player_name",
        "season",
        "position",
        "games_played",
        "toi_per_game",
        "game_score_per_60",
        "game_score_per_60_above_replacement",
        "points_per_60",
        "points_per_60_above_replacement",
        "xg_per_60",
        "xg_per_60_above_replacement",
        "on_ice_expected_goals_pct",
        "on_ice_expected_goals_pct_above_replacement",
        "is_replacement_pool",
    ]

    sample = (
        df[df["eligible_for_training"]][sample_columns]
        .sort_values(
            "game_score_per_60_above_replacement",
            ascending=False,
        )
        .head(15)
    )

    print(sample.to_string(index=False))


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="replacement level")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    try:
        settings = read_logging_settings(load_environment())
    except LoggingSettingsError as error:
        parser.error(str(error))
    configure_logging(settings)
    context = start_command("ml.replacement_level")
    try:
        replacement_data = calculate_replacement_level()
        report_ml_progress(
            context,
            event="ml.dataset_ready",
            stage="replacement_level",
            values={"rows": len(replacement_data)},
        )
        print_replacement_diagnostics(replacement_data)
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

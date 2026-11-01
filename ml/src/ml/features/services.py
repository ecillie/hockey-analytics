"""Feature and replacement calculations over owned dataframe copies."""

import pandas as pd
import numpy as np

from ml.domain import FeatureOptions, HIGHER_IS_BETTER, LOWER_IS_BETTER
from ml.errors import ReplacementPercentileError
from ml.features.util import calculate_per_60, group_player_positions
from ml.pipelines.services import build_model_dataset
from ml.schemas import validate_feature_options, validate_frame

REPLACEMENT_FEATURES = HIGHER_IS_BETTER + LOWER_IS_BETTER


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
        features["position_group"] = group_player_positions(features["position"])

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

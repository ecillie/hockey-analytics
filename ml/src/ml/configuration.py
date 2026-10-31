"""Immutable feature selection and model configuration."""

from dataclasses import dataclass

MODEL_FEATURE_COLUMNS = (
    "games_played",
    "toi_hours",
    "goals_per_60",
    "assists_per_60",
    "points_per_60",
    "xg_per_60",
    "shots_on_goal_per_60",
    "unblocked_attempts_per_60",
    "game_score_per_60",
    "primary_assists_per_60",
    "secondary_assists_per_60",
    "takeaways_per_60",
    "giveaways_per_60",
    "net_takeaways_per_60",
    "blocks_per_60",
    "penalties_per_60",
    "penalties_drawn_per_60",
    "penalty_differential_per_60",
    "goals_above_expected_per_60",
    "on_ice_expected_goals_pct",
    "offensive_zone_start_pct",
    "defensive_zone_start_pct",
    "neutral_zone_start_pct",
)

HIGHER_IS_BETTER = (
    "goals_per_60",
    "primary_assists_per_60",
    "secondary_assists_per_60",
    "points_per_60",
    "xg_per_60",
    "shots_on_goal_per_60",
    "unblocked_attempts_per_60",
    "game_score_per_60",
    "takeaways_per_60",
    "blocks_per_60",
    "penalties_drawn_per_60",
    "penalty_differential_per_60",
    "goals_above_expected_per_60",
    "on_ice_expected_goals_pct",
)

LOWER_IS_BETTER = ("giveaways_per_60", "penalties_per_60")

NUMERIC_FEATURES = (
    "games_played",
    "toi_hours",
    "toi_per_game",
    "goals_per_60",
    "primary_assists_per_60",
    "secondary_assists_per_60",
    "points_per_60",
    "xg_per_60",
    "shots_on_goal_per_60",
    "unblocked_attempts_per_60",
    "game_score_per_60",
    "takeaways_per_60",
    "giveaways_per_60",
    "net_takeaways_per_60",
    "blocks_per_60",
    "penalties_per_60",
    "penalties_drawn_per_60",
    "penalty_differential_per_60",
    "goals_above_expected_per_60",
    "on_ice_expected_goals_pct",
    "offensive_zone_start_pct",
    "defensive_zone_start_pct",
    "neutral_zone_start_pct",
    "goals_per_60_above_replacement",
    "primary_assists_per_60_above_replacement",
    "secondary_assists_per_60_above_replacement",
    "points_per_60_above_replacement",
    "xg_per_60_above_replacement",
    "game_score_per_60_above_replacement",
    "takeaways_per_60_above_replacement",
    "giveaways_per_60_above_replacement",
    "blocks_per_60_above_replacement",
    "penalties_per_60_above_replacement",
    "penalties_drawn_per_60_above_replacement",
    "penalty_differential_per_60_above_replacement",
    "goals_above_expected_per_60_above_replacement",
    "on_ice_expected_goals_pct_above_replacement",
)

CATEGORICAL_FEATURES = ("position_group",)


@dataclass(slots=True, kw_only=True, frozen=True)
class ModelOptions:
    learning_rate: float = 0.05
    max_iter: int = 300
    max_leaf_nodes: int = 31
    l2_regularization: float = 1.0
    random_state: int = 42


@dataclass(slots=True, kw_only=True, frozen=True)
class FeatureOptions:
    minimum_training_games: int = 20
    replacement_percentile: float = 0.20
    salary_cap_normalization_dollars: float = 100_000_000.0


@dataclass(slots=True, kw_only=True, frozen=True)
class MetricTolerance:
    mae: float = 0.25
    rmse: float = 0.35
    r2: float = 0.05

    @property
    def values(self) -> dict[str, float]:
        return {"mae": self.mae, "rmse": self.rmse, "r2": self.r2}

"""Feature rates, eligibility, replacement isolation, and cap joins."""

import numpy as np
import pandas as pd
import pytest
from ml.features.build_features import (
    MODEL_FEATURE_COLUMNS,
    build_features,
    get_training_dataset,
)
from ml.features.replacement_level import (
    calculate_replacement_level,
    print_replacement_diagnostics,
)
from ml.configuration import FeatureOptions
from ml.pipelines.build_model_dataset import (
    FORBIDDEN_CONTRACT_COLUMNS,
    build_model_dataset,
)
from ml.tests.fakes import (
    DatasetScenario,
)


class TestFeatureRates:
    @pytest.fixture
    def features(self, player_seasons):
        return build_features(player_seasons)

    def test_features_preserve_nulls_and_make_zero_toi_safe(self, features):
        assert pd.isna(features.loc[0, "goals_per_60"])
        assert pd.isna(features.loc[1, "points_per_60"])
        assert not np.isinf(features.select_dtypes("number").to_numpy()).any()

    @pytest.fixture
    def hourly_row(self, player_seasons):
        return player_seasons.iloc[[2]].assign(
            ice_time_seconds=3600, goals=12, assists=18, points=30
        )

    def test_per_60_features_use_seconds_and_preserve_expected_rates(self, hourly_row):
        result = build_features(hourly_row).iloc[0]
        assert result["toi_minutes"] == pytest.approx(60.0)
        assert result["toi_hours"] == pytest.approx(1.0)
        assert result["goals_per_60"] == pytest.approx(12.0)
        assert result["assists_per_60"] == pytest.approx(18.0)
        assert result["points_per_60"] == pytest.approx(30.0)
        assert result["goals_above_expected"] == pytest.approx(
            12 - result["individual_expected_goals"]
        )

    @pytest.fixture
    def missing_zone_starts(self, player_seasons):
        player_seasons.loc[
            0,
            [
                "offensive_zone_shift_starts",
                "defensive_zone_shift_starts",
                "neutral_zone_shift_starts",
            ],
        ] = None
        player_seasons.loc[1, "position"] = "X"
        return player_seasons

    def test_features_handle_missing_zone_starts_and_unmapped_positions(
        self, missing_zone_starts
    ):
        result = build_features(missing_zone_starts)
        assert pd.isna(result.loc[0, "offensive_zone_start_pct"])
        assert pd.isna(result.loc[1, "position_group"])
        assert result.loc[0, "eligible_for_training"]

    def test_feature_columns_are_finite_when_defined(self, features):
        for column in MODEL_FEATURE_COLUMNS:
            assert np.isfinite(features[column].dropna().to_numpy()).all(), column

    @pytest.fixture
    def under_minimum_games(self, player_seasons):
        player_seasons.loc[player_seasons.index[0], "games_played"] = 19
        return player_seasons

    def test_minimum_games_eligibility(self, under_minimum_games):
        result = get_training_dataset(under_minimum_games)
        assert result["games_played"].min() >= 20

    @pytest.fixture
    def zero_toi(self, player_seasons):
        player_seasons.loc[1, "games_played"] = 82
        return player_seasons

    def test_zero_toi_is_not_training_eligible_even_with_enough_games(self, zero_toi):
        result = build_features(zero_toi)
        assert not result.loc[1, "eligible_for_training"]
        assert len(get_training_dataset(zero_toi)) == len(zero_toi) - 1


class TestReplacementLevels:
    comparable_columns = (
        "replacement_toi_per_game_threshold",
        "replacement_points_per_60",
        "points_per_60_above_replacement",
    )

    @pytest.fixture
    def baseline(self, player_seasons):
        return calculate_replacement_level(player_seasons)

    def test_position_grouping_and_replacement_level(self, baseline):
        assert set(baseline["position_group"].dropna()) == {"forward", "defense"}
        assert baseline["replacement_toi_per_game_threshold"].notna().any()
        assert (baseline["game_score_per_60_above_replacement"].dropna() >= 0).any()

    def test_replacement_baselines_are_position_and_season_specific(self, baseline):
        grouped = baseline.dropna(subset=["replacement_points_per_60"])
        assert (
            grouped.groupby(["season", "position_group"])["replacement_points_per_60"]
            .nunique()
            .eq(1)
            .all()
        )
        assert grouped["replacement_points_per_60"].notna().all()

    @pytest.fixture
    def with_contracts(self, player_seasons):
        return player_seasons.assign(
            cap_hit_cents=np.arange(len(player_seasons)) * 1000,
            contract_id=np.arange(len(player_seasons)),
        )

    def test_replacement_calculation_does_not_use_contract_data(
        self, baseline, with_contracts
    ):
        result = calculate_replacement_level(with_contracts)
        pd.testing.assert_frame_equal(
            baseline[list(self.comparable_columns)],
            result[list(self.comparable_columns)],
            check_dtype=False,
        )

    @pytest.fixture
    def future_changed(self, player_seasons):
        player_seasons.loc[player_seasons["season"] == 2025, "game_score"] = 10_000
        return player_seasons

    def test_replacement_levels_are_isolated_by_season(self, baseline, future_changed):
        changed = calculate_replacement_level(future_changed)
        prior = baseline["season"] < 2025
        pd.testing.assert_frame_equal(
            baseline.loc[prior, list(self.comparable_columns)].reset_index(drop=True),
            changed.loc[prior, list(self.comparable_columns)].reset_index(drop=True),
            check_dtype=False,
        )


class TestModelDataset:
    @pytest.fixture
    def single_cap(self):
        return pd.DataFrame(
            {
                "season": [2021],
                "season_label": ["2021-22"],
                "salary_cap_cents": [1000],
                "salary_cap_dollars": [10],
            }
        )

    @pytest.fixture
    def duplicate(self, player_seasons, single_cap):
        return DatasetScenario(
            players=pd.concat(
                [player_seasons.head(1), player_seasons.head(1)], ignore_index=True
            ),
            caps=single_cap,
        )

    def test_model_dataset_rejects_duplicate_player_seasons(self, duplicate):
        with pytest.raises(RuntimeError, match="duplicate"):
            build_model_dataset(players=duplicate.players, salary_cap=duplicate.caps)

    @pytest.fixture
    def annual_caps(self):
        return pd.DataFrame(
            {
                "season": range(2021, 2026),
                "season_label": [f"{year}-{year + 1}" for year in range(2021, 2026)],
                "salary_cap_cents": [1000, 1100, 1200, 1300, 1400],
                "salary_cap_dollars": [10, 11, 12, 13, 14],
            }
        )

    def test_model_dataset_joins_cap_by_season_without_contract_columns(
        self, player_seasons, annual_caps
    ):
        result = build_model_dataset(players=player_seasons, salary_cap=annual_caps)
        assert result.groupby("season")["salary_cap_dollars"].first().to_dict() == {
            2021: 10,
            2022: 11,
            2023: 12,
            2024: 13,
            2025: 14,
        }
        assert result.groupby("season")["salary_cap_fraction"].first().to_dict() == {
            2021: 0.0000001,
            2022: 0.00000011,
            2023: 0.00000012,
            2024: 0.00000013,
            2025: 0.00000014,
        }
        assert not FORBIDDEN_CONTRACT_COLUMNS.intersection(result.columns)
        assert result["salary_cap_fraction"].iloc[0] == pytest.approx(10 / 100_000_000)

    @pytest.fixture
    def fixed_scale(self, player_seasons):
        caps = pd.DataFrame(
            {
                "season": [2021, 2022],
                "season_label": ["2021-22", "2022-23"],
                "salary_cap_cents": [10_000, 20_000],
                "salary_cap_dollars": [100, 200],
            }
        )
        return DatasetScenario(
            players=player_seasons[player_seasons["season"].isin([2021, 2022])],
            caps=caps,
        )

    def test_salary_cap_normalization_uses_fixed_scale_not_dataset_max(
        self, fixed_scale
    ):
        result = build_model_dataset(
            players=fixed_scale.players, salary_cap=fixed_scale.caps
        )
        assert result.groupby("season")["salary_cap_fraction"].first().to_dict() == {
            2021: 100 / 100_000_000,
            2022: 200 / 100_000_000,
        }

    @pytest.fixture
    def leaked(self, player_seasons, single_cap):
        return DatasetScenario(
            players=player_seasons.head(1).assign(cap_hit_cents=123), caps=single_cap
        )

    def test_model_dataset_rejects_contract_leakage(self, leaked):
        with pytest.raises(RuntimeError, match="Contract data leaked"):
            build_model_dataset(players=leaked.players, salary_cap=leaked.caps)

    @pytest.fixture
    def missing_cap(self, player_seasons, single_cap):
        return DatasetScenario(
            players=pd.concat(
                [
                    player_seasons.head(1),
                    player_seasons[player_seasons["season"] == 2022].head(1),
                ]
            ),
            caps=single_cap,
        )

    def test_missing_cap_history_remains_null_and_does_not_create_infinity(
        self, missing_cap
    ):
        result = build_model_dataset(
            players=missing_cap.players, salary_cap=missing_cap.caps
        )
        assert result.loc[result["season"] == 2022, "salary_cap_fraction"].isna().all()
        assert not np.isinf(result["salary_cap_fraction"].dropna()).any()


class TestReplacementDiagnostics:
    @pytest.fixture(
        params=[
            pytest.param((None, None, 0.20), id="default"),
            pytest.param((None, 0.75, 0.75), id="options-override"),
            pytest.param((0.5, 0.75, 0.5), id="explicit-override-wins"),
            pytest.param((0.0, None, 0.0), id="zero-boundary"),
            pytest.param((1.0, None, 1.0), id="one-boundary"),
        ]
    )
    def scenario(self, request, player_seasons):
        explicit, configured, expected = request.param
        options = (
            FeatureOptions()
            if configured is None
            else FeatureOptions(replacement_percentile=configured)
        )
        result = calculate_replacement_level(player_seasons, explicit, options=options)
        return result, expected

    def test_diagnostics_report_the_percentile_used_for_calculation(
        self, scenario, capsys
    ):
        result, expected = scenario
        print_replacement_diagnostics(result)
        assert f"Replacement percentile: {expected:.0%}" in capsys.readouterr().out
        assert result.attrs["replacement_percentile"] == expected

    def test_thresholds_use_the_effective_percentile(self, scenario):
        result, expected = scenario
        eligible = result[
            result["eligible_for_training"]
            & result["position_group"].notna()
            & result["toi_per_game"].notna()
        ]
        actual = eligible.groupby(["season", "position_group"])[
            "replacement_toi_per_game_threshold"
        ].first()
        calculated = eligible.groupby(["season", "position_group"])[
            "toi_per_game"
        ].quantile(expected)
        pd.testing.assert_series_equal(actual, calculated, check_names=False)

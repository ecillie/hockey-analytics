"""Temporal targets, deterministic training, prediction, and artifact contracts."""

import json
from importlib.resources import files
import joblib
import numpy as np
import pandas as pd
import pytest
from ml.evaluation.evaluate_skater_model import metrics
from ml.evaluation.gate import (
    check_metric_regression,
    prediction_frame,
    stable_metadata_json,
    temporal_splits,
    validate_metadata,
)
from ml.training.train_skater_value import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    build_model,
    build_training_data,
)
from ml.tests.fakes import (
    TrainedScenario,
)


class TestTemporalTraining:
    columns = NUMERIC_FEATURES + CATEGORICAL_FEATURES

    @pytest.fixture
    def data(self, player_seasons):
        return build_training_data(player_seasons)

    def test_season_join_has_no_future_leakage(self, data, player_seasons):
        assert (data["target_season"] == data["season"] + 1).all()
        assert data["target_season"].max() <= player_seasons["season"].max()
        assert not (data["season"] >= data["target_season"]).any()

    @pytest.fixture
    def missing_next(self, player_seasons):
        return player_seasons[
            ~((player_seasons["player_id"] == 4) & (player_seasons["season"] == 2022))
        ]

    def test_missing_next_season_is_zero_target(self, missing_next):
        result = build_training_data(missing_next)
        row = result[(result["player_id"] == 4) & (result["season"] == 2021)].iloc[0]
        assert row["target_season"] == 2022
        assert row["next_season_hockey_value"] == 0.0

    def test_training_rows_are_eligible_and_model_columns_exclude_contracts(self, data):
        assert data["eligible_for_training"].all()
        assert not {"cap_hit_cents", "aav", "contract_id"}.intersection(self.columns)

    @pytest.fixture
    def splits(self, data):
        return temporal_splits(data)

    def test_temporal_train_validation_test_splits(self, data, splits):
        assert (
            splits["train"]["target_season"].max()
            < splits["validation"]["target_season"].min()
        )
        assert (
            splits["validation"]["target_season"].max()
            < splits["test"]["target_season"].min()
        )
        assert set(splits) == {"train", "validation", "test"}
        assert sum(len(part) for part in splits.values()) == len(data)

    @pytest.fixture
    def trained(self, splits):
        train = splits["train"][list(self.columns)]
        target = splits["train"]["next_season_hockey_value"]
        return TrainedScenario(
            model=build_model().fit(train, target),
            repeated=build_model().fit(train, target),
            test=splits["test"],
        )

    def test_training_is_deterministic_and_predictions_are_safe(self, trained):
        predictions = trained.model.predict(trained.test[list(self.columns)])
        assert np.array_equal(
            predictions, trained.repeated.predict(trained.test[list(self.columns)])
        )
        frame = prediction_frame(trained.test, predictions)
        assert list(frame.columns) == ["player_id", "season", "prediction"]
        assert np.isfinite(frame["prediction"]).all()
        assert (frame["prediction"] >= 0).all()

    def test_model_seed_is_explicit_and_serialization_round_trips(
        self, trained, tmp_path
    ):
        assert trained.model.named_steps["model"].random_state == 42
        before = trained.model.predict(trained.test[list(self.columns)])
        path = tmp_path.joinpath("model.joblib")
        joblib.dump(trained.model, path)
        after = joblib.load(path).predict(trained.test[list(self.columns)])
        assert np.array_equal(before, after)

    @pytest.fixture
    def insufficient_seasons(self):
        return pd.DataFrame({"target_season": [2024, 2025]})

    def test_temporal_split_requires_three_seasons(self, insufficient_seasons):
        with pytest.raises(ValueError, match="three"):
            temporal_splits(insufficient_seasons)


class TestPredictionBoundaries:
    @pytest.fixture
    def rows(self, player_seasons):
        return player_seasons.head(2).assign(target_season=2022)

    @pytest.fixture(
        params=[
            pytest.param(np.array([np.nan]), id="nonfinite"),
            pytest.param(np.array([1.0, 2.0]), id="wrong-length"),
        ]
    )
    def invalid_values(self, request):
        return request.param

    def test_prediction_invariants_reject_bad_values(self, rows, invalid_values):
        with pytest.raises(ValueError):
            prediction_frame(rows.head(1), invalid_values)

    @pytest.fixture
    def negative_values(self):
        return np.array([-3.0, 2.0])

    def test_prediction_frame_clips_negative_values(self, rows, negative_values):
        frame = prediction_frame(rows, negative_values)
        assert frame["prediction"].tolist() == [0.0, 2.0]


class TestMetricRegression:
    @pytest.fixture
    def known_metrics(self):
        return metrics(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 2.0]))

    def test_metrics_and_regression_thresholds(self, known_metrics):
        assert known_metrics["mae"] == pytest.approx(1 / 3)
        assert known_metrics["rmse"] == pytest.approx((1 / 3) ** 0.5)
        assert known_metrics["r2"] == pytest.approx(0.5)
        check_metric_regression(known_metrics, {"mae": 1.0, "rmse": 1.0, "r2": -1.0})

    @pytest.fixture(
        params=[
            pytest.param(
                (
                    {"mae": 2.0, "rmse": 1.0, "r2": 0.0},
                    {"mae": 1.0, "rmse": 1.0, "r2": 0.0},
                    {"mae": 0.1, "rmse": 0.1, "r2": 0.1},
                    "mae",
                ),
                id="mae-worsens",
            ),
            pytest.param(
                (
                    {"mae": 1.0, "rmse": 1.0, "r2": 0.49},
                    {"mae": 1.0, "rmse": 1.0, "r2": 0.5},
                    {"mae": 0.0, "rmse": 0.0, "r2": 0.01},
                    "r2",
                ),
                id="r2-worsens-downwards",
            ),
        ]
    )
    def regression(self, request):
        return request.param

    def test_metric_regression_uses_worse_direction(self, regression):
        current, baseline, tolerances, metric = regression
        with pytest.raises(AssertionError, match=metric):
            check_metric_regression(current, baseline, tolerances)

    @pytest.fixture
    def unchanged_metrics(self):
        return {"mae": 1.0, "rmse": 1.0, "r2": 0.5}

    def test_equal_metrics_pass_with_zero_tolerance(self, unchanged_metrics):
        check_metric_regression(
            unchanged_metrics, unchanged_metrics, {"mae": 0.0, "rmse": 0.0, "r2": 0.0}
        )


class TestMetadataContract:
    @pytest.fixture
    def metadata(self):
        return json.loads(
            files("ml")
            .joinpath("resources/skater_value_model_metadata.json")
            .read_text(encoding="utf-8")
        )

    def test_metadata_is_stable_and_valid(self, metadata):
        validate_metadata(metadata)
        assert stable_metadata_json(metadata) == stable_metadata_json(
            json.loads(stable_metadata_json(metadata))
        )

    @pytest.fixture(
        params=[
            pytest.param("contract", id="contract-leakage"),
            pytest.param("split", id="reversed-splits"),
            pytest.param("incomplete", id="missing-metric"),
            pytest.param("nonfinite", id="nonfinite-metric"),
        ]
    )
    def invalid_metadata(self, metadata, request):
        if request.param == "contract":
            metadata["contract_features_used"] = True
            return metadata, "Contract"
        if request.param == "split":
            metadata.update(validation_target_season=2025, test_target_season=2024)
            return metadata, "Validation"
        if request.param == "incomplete":
            metadata["metrics"]["test"].pop("rmse")
            return metadata, "rmse"
        metadata["metrics"]["validation"]["r2"] = float("nan")
        return metadata, "finite"

    def test_metadata_validation_rejects_invalid_boundaries(self, invalid_metadata):
        metadata, message = invalid_metadata
        with pytest.raises(ValueError, match=message):
            validate_metadata(metadata)

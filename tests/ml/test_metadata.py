"""Immutable metadata, published serialization, and structured model failures."""

import json
from importlib.resources import files
import joblib
import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from ml.tests.strategies import generate_identical_metric_inputs
from pydantic import ValidationError
from ml.artifacts import ArtifactPaths, load_model
from ml.domain import Metric, Split
from ml.configuration import FeatureOptions
from ml.training.train_skater_value import build_training_data, train_model
from ml.errors import (
    ContractFeaturesError,
    TrainingRowsError,
    TrainingTargetsError,
    MinimumGamesError,
    ReplacementPercentileError,
    SalaryCapNormalizationError,
    FeatureOrderError,
    InsufficientSeasonsError,
    InvalidMetricError,
    InvalidTargetSeasonsError,
    MetricRegressionError,
    MissingMetricError,
    MissingTargetSeasonError,
    ModelArtifactError,
    ModelIdentityError,
    SplitOrderError,
)
from ml.evaluation.gate import (
    check_metric_regression,
    serialize_metadata_json,
    split_temporal_data,
    validate_metadata,
)
from ml.schemas import ModelMetadata, validate_feature_options


class TestMetadataValues:
    @pytest.fixture
    def committed_text(self):
        return (
            files("ml")
            .joinpath("resources/skater_value_model_metadata.json")
            .read_text()
        )

    @pytest.fixture
    def payload(self, committed_text):
        return json.loads(committed_text)

    @pytest.fixture
    def parsed(self, payload):
        return validate_metadata(payload)

    def test_validation_returns_owned_immutable_nested_values(self, parsed, payload):
        original = serialize_metadata_json(parsed)
        payload["metrics"]["train"]["mae"] = 999
        payload["metrics"].clear()
        payload["numeric_features"].clear()
        assert serialize_metadata_json(parsed) == original
        assert isinstance(parsed, ModelMetadata)
        with pytest.raises(ValidationError):
            setattr(parsed.metrics, "train", parsed.metrics.test)
        with pytest.raises(ValidationError):
            setattr(parsed.metrics.train, "mae", 999)
        with pytest.raises(ValidationError):
            setattr(parsed, "numeric_features", ())

    def test_serialization_preserves_exact_committed_json(self, committed_text, parsed):
        assert (
            serialize_metadata_json(parsed)
            == json.dumps(json.loads(committed_text), indent=2, sort_keys=True) + "\n"
        )
        assert validate_metadata(json.loads(serialize_metadata_json(parsed))) == parsed
        assert tuple(map(str, Split)) == ("train", "validation", "test")
        assert tuple(map(str, Metric)) == ("mae", "rmse", "r2")
        assert (
            parsed.metrics.split_values(Split.TEST).metric_value(Metric.MAE)
            == parsed.metrics.test.mae
        )

    @pytest.fixture(
        params=[
            pytest.param(
                ("contract_features_used", True, ContractFeaturesError), id="contract"
            ),
            pytest.param(
                ("numeric_features", [], FeatureOrderError), id="numeric-order"
            ),
            pytest.param(
                ("categorical_features", [], FeatureOrderError), id="categorical-order"
            ),
            pytest.param(
                ("validation_target_season", 9999, SplitOrderError), id="split-order"
            ),
            pytest.param(
                ("model_type", "unknown", ModelIdentityError), id="model-type"
            ),
            pytest.param(("target", "unknown", ModelIdentityError), id="target"),
        ]
    )
    def incompatible(self, payload, request):
        field, value, error = request.param
        payload[field] = value
        return payload, error

    def test_incompatible_metadata_has_distinct_failures(self, incompatible):
        payload, error = incompatible
        with pytest.raises(error) as raised:
            validate_metadata(payload)
        assert len(vars(raised.value)) > 0

    @pytest.fixture(
        params=[
            pytest.param(("train", "rows", 0), id="zero-rows"),
            pytest.param(("test", "rows", -1), id="negative-rows"),
            pytest.param(("test", "rows", 1.5), id="fractional-rows"),
            pytest.param(("train", "mae", np.inf), id="infinite-mae"),
            pytest.param(("validation", "rmse", np.nan), id="nan-rmse"),
            pytest.param(("test", "r2", -np.inf), id="infinite-r2"),
        ]
    )
    def invalid_metric(self, request, payload):
        split, metric, value = request.param
        payload["metrics"][split][metric] = value
        return payload

    def test_metric_validation_rejects_invalid_rows_and_values(self, invalid_metric):
        with pytest.raises(ValidationError):
            validate_metadata(invalid_metric)

    @pytest.fixture(
        params=[
            pytest.param("missing", id="missing-split"),
            pytest.param("extra", id="extra-split"),
        ]
    )
    def invalid_splits(self, request, payload):
        if request.param == "missing":
            payload["metrics"].pop("test")
            return payload
        payload["metrics"]["extra"] = payload["metrics"]["test"]
        return payload

    def test_metrics_require_exact_split_set(self, invalid_splits):
        with pytest.raises(ValidationError):
            validate_metadata(invalid_splits)

    @pytest.fixture
    def invalid_artifact(self, tmp_path, committed_text):
        paths = ArtifactPaths(
            model=tmp_path.joinpath("model.joblib"),
            metadata=tmp_path.joinpath("metadata.json"),
        )
        paths.metadata.write_text(committed_text)
        joblib.dump(7, paths.model)
        return paths

    def test_artifact_failure_retains_actual_type(self, invalid_artifact):
        with pytest.raises(ModelArtifactError) as raised:
            load_model(invalid_artifact)
        assert raised.value.actual_type is int


class TestTemporalFailures:
    @pytest.fixture(
        params=[
            pytest.param(({}, MissingTargetSeasonError, "columns", ()), id="missing"),
            pytest.param(
                (
                    {"target_season": [2022, 2023]},
                    InsufficientSeasonsError,
                    "seasons",
                    (2022, 2023),
                ),
                id="insufficient",
            ),
            pytest.param(
                (
                    {"target_season": [2022, np.inf, np.nan, 2023.5]},
                    InvalidTargetSeasonsError,
                    "invalid_rows",
                    3,
                ),
                id="nonfinite-and-fractional",
            ),
        ]
    )
    def scenario(self, request):
        data, error, field, expected = request.param
        return pd.DataFrame(data), error, field, expected

    def test_failures_retain_context(self, scenario):
        data, error, field, expected = scenario
        with pytest.raises(error) as raised:
            split_temporal_data(data)
        assert getattr(raised.value, field) == expected


class TestMetricFailures:
    @pytest.fixture(
        params=[
            pytest.param(
                ({}, {"mae": 0.0}, {"mae": 0.0}, MissingMetricError),
                id="missing-current",
            ),
            pytest.param(
                ({"mae": 0.0}, {}, {"mae": 0.0}, MissingMetricError),
                id="missing-baseline",
            ),
            pytest.param(
                ({"mae": 0.0}, {"mae": 0.0}, {}, MissingMetricError),
                id="missing-tolerance",
            ),
            pytest.param(
                ({"mae": np.inf}, {"mae": 0.0}, {"mae": 0.0}, InvalidMetricError),
                id="nonfinite-current",
            ),
            pytest.param(
                ({"mae": 0.0}, {"mae": np.nan}, {"mae": 0.0}, InvalidMetricError),
                id="nonfinite-baseline",
            ),
            pytest.param(
                ({"mae": 0.0}, {"mae": 0.0}, {"mae": -1.0}, InvalidMetricError),
                id="negative-tolerance",
            ),
            pytest.param(
                ({"mae": 0.0}, {"mae": 0.0}, {"mae": np.inf}, InvalidMetricError),
                id="nonfinite-tolerance",
            ),
            pytest.param(
                ({"mae": 2.0}, {"mae": 0.0}, {"mae": 1.0}, MetricRegressionError),
                id="regression",
            ),
        ]
    )
    def scenario(self, request):
        return request.param

    def test_errors_identify_metric(self, scenario):
        current, baseline, tolerance, error = scenario
        with pytest.raises(error) as raised:
            check_metric_regression(current, baseline, tolerance)
        assert raised.value.metric == Metric.MAE

    @given(inputs=generate_identical_metric_inputs())
    def test_identical_finite_metrics_never_regress(self, inputs):
        check_metric_regression(*inputs)


class TestTrainingFailures:
    @pytest.fixture
    def empty_players(self, player_seasons):
        return player_seasons.head(0)

    @pytest.fixture
    def invalid_targets(self, player_seasons):
        return build_training_data(player_seasons).assign(
            next_season_hockey_value=np.nan
        )

    def test_empty_training_failure_exposes_row_count(self, empty_players):
        with pytest.raises(TrainingRowsError) as raised:
            build_training_data(empty_players)
        assert raised.value.rows == 0

    def test_missing_targets_fail_before_fitting(self, invalid_targets):
        with pytest.raises(TrainingTargetsError) as raised:
            train_model(invalid_targets)
        assert raised.value.invalid_rows == len(invalid_targets)


class TestFeatureOptions:
    @pytest.fixture(
        params=[
            pytest.param(
                (FeatureOptions(minimum_training_games=0), MinimumGamesError, 0),
                id="minimum-games",
            ),
            pytest.param(
                (
                    FeatureOptions(replacement_percentile=-0.1),
                    ReplacementPercentileError,
                    -0.1,
                ),
                id="percentile",
            ),
            pytest.param(
                (
                    FeatureOptions(salary_cap_normalization_dollars=np.inf),
                    SalaryCapNormalizationError,
                    np.inf,
                ),
                id="salary-cap",
            ),
        ]
    )
    def scenario(self, request):
        return request.param

    def test_option_failures_expose_effective_value(self, scenario):
        options, error, expected = scenario
        with pytest.raises(error) as raised:
            validate_feature_options(options)
        assert raised.value.value == expected

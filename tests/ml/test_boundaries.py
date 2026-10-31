"""Behavior at ML data, configuration, and artifact boundaries."""

import json
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from importlib import import_module
from importlib.resources import files
from ml.tests.fakes import PipelineResources, ReadScenario

import numpy as np
import pandas as pd
import pytest
from app.config import AppEnvironment, DatabaseSettings
from ml.artifacts import ArtifactPaths, load_model, save_model, save_predictions
from ml.configuration import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    FeatureOptions,
    ModelOptions,
)
from ml.errors import FrameColumnsError, FrameGrainError, FrameValuesError
from ml.evaluation.evaluate_skater_model import evaluate_model, evaluate_predictions
from ml.evaluation.gate import prediction_frame, temporal_splits, validate_metadata
from ml.features.build_features import build_features
from ml.features.replacement_level import calculate_replacement_level
from ml.pipelines.build_model_dataset import build_model_dataset
from ml.pipelines.run_pipeline import run_pipeline
from ml.training.train_skater_value import (
    build_model,
    build_training_data,
    train,
    train_model,
)


class TestDataBoundaries:
    @pytest.fixture
    def caps(self):
        return pd.DataFrame(
            {
                "season": range(2021, 2026),
                "season_label": [str(year) for year in range(2021, 2026)],
                "salary_cap_cents": [8_000_000_000] * 5,
                "salary_cap_dollars": [80_000_000] * 5,
            }
        )

    @pytest.fixture
    def counted_reads(self, monkeypatch, player_seasons, caps):
        module = import_module("ml.pipelines.run_pipeline")
        scenario = ReadScenario(connection=object())
        calls = scenario.calls
        connection = scenario.connection
        settings = DatabaseSettings(
            environment=AppEnvironment.DEV,
            database_url="postgresql://unused/tradevalue_test_ml",
        )

        def read_settings() -> DatabaseSettings:
            return settings

        def read_players(min_games=1, *, connection):
            calls.append(("players", connection))
            return player_seasons

        def read_caps(*, connection):
            calls.append(("caps", connection))
            return caps

        @contextmanager
        def resources(selected_settings) -> Generator[PipelineResources]:
            assert selected_settings is settings
            calls.append(("opened", connection))
            yield PipelineResources(connection=connection)
            calls.append(("closed", connection))

        monkeypatch.setenv("ENV", "")
        monkeypatch.setattr(module, "get_database_settings", read_settings)
        monkeypatch.setattr(module, "database_resources", resources)
        monkeypatch.setattr(module, "load_player_stats", read_players)
        monkeypatch.setattr(module, "load_salary_cap", read_caps)
        return scenario

    def test_reads_each_source_once_and_closes_shared_connection(self, counted_reads):
        calls, connection = counted_reads.calls, counted_reads.connection
        result = run_pipeline()
        assert len(result) == 20
        assert calls == [
            ("opened", connection),
            ("players", connection),
            ("caps", connection),
            ("closed", connection),
        ]

    def test_loaded_frames_do_not_open_database(
        self, player_seasons, caps, counted_reads
    ):
        before = player_seasons.copy(deep=True)
        before_caps = caps.copy(deep=True)
        result = run_pipeline(players=player_seasons, salary_caps=caps)
        assert counted_reads.calls == []
        assert len(result) == len(player_seasons)
        pd.testing.assert_frame_equal(before, player_seasons)
        pd.testing.assert_frame_equal(before_caps, caps)

    def test_stage_computation_does_not_mutate_input(self, player_seasons):
        before = player_seasons.copy(deep=True)
        calculate_replacement_level(player_seasons)
        build_training_data(player_seasons)
        pd.testing.assert_frame_equal(before, player_seasons)

    @pytest.fixture(
        params=[
            pytest.param("missing", id="missing-column"),
            pytest.param("duplicate", id="duplicate-grain"),
            pytest.param("infinite", id="nonfinite-input"),
            pytest.param("null-key", id="null-key"),
        ]
    )
    def malformed(self, request, player_seasons):
        if request.param == "missing":
            return player_seasons.drop(columns="goals"), FrameColumnsError
        if request.param == "duplicate":
            return pd.concat([player_seasons, player_seasons.head(1)]), FrameGrainError
        if request.param == "null-key":
            return player_seasons.assign(player_id=None), FrameGrainError
        return player_seasons.assign(goals=np.inf), FrameValuesError

    def test_features_reject_malformed_frame(self, malformed):
        frame, error = malformed
        with pytest.raises(error):
            build_features(frame)

    def test_injected_frames_obey_minimum_games(self, player_seasons, caps):
        result = build_model_dataset(25, players=player_seasons, salary_cap=caps)
        assert len(result) == 10
        assert result["games_played"].ge(25).all()

    @pytest.fixture(
        params=[
            pytest.param(-0.1, id="negative"),
            pytest.param(1.1, id="over-one"),
            pytest.param(np.nan, id="nan"),
        ]
    )
    def invalid_percentile(self, request):
        return request.param

    def test_replacement_rejects_invalid_percentile(
        self, player_seasons, invalid_percentile
    ):
        with pytest.raises(ValueError, match="percentile"):
            calculate_replacement_level(player_seasons, invalid_percentile)

    def test_options_are_immutable_and_defaults_preserve_model(self):
        options = ModelOptions()
        with pytest.raises(FrozenInstanceError):
            setattr(options, "random_state", 7)
        model = build_model()
        regressor = model.named_steps["model"]
        assert (
            regressor.learning_rate,
            regressor.max_iter,
            regressor.max_leaf_nodes,
            regressor.l2_regularization,
            regressor.random_state,
        ) == (0.05, 300, 31, 1.0, 42)

    def test_training_eligibility_can_be_injected(self, player_seasons):
        result = build_features(
            player_seasons, options=FeatureOptions(minimum_training_games=27)
        )
        assert not result["eligible_for_training"].any()


class TestArtifacts:
    @pytest.fixture
    def training_data(self, player_seasons):
        return build_training_data(player_seasons)

    @pytest.fixture
    def trained(self, training_data):
        return train_model(training_data, options=ModelOptions(max_iter=5))

    @pytest.fixture
    def paths(self, tmp_path):
        return ArtifactPaths(
            model=tmp_path.joinpath("models", "model.joblib"),
            metadata=tmp_path.joinpath("metadata", "model.json"),
        )

    def test_training_is_silent_and_has_no_artifact_side_effects(
        self, player_seasons, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.chdir(tmp_path)
        train(player_seasons, options=ModelOptions(max_iter=5))
        assert list(tmp_path.iterdir()) == []
        assert capsys.readouterr().out == ""

    def test_explicit_artifacts_round_trip_and_evaluation_owns_data(
        self, trained, training_data, paths, tmp_path
    ):
        save_model(trained.model, trained.metadata, paths)
        model, metadata = load_model(paths)
        assert paths.metadata.read_text() == trained.metadata_json
        before = training_data.copy(deep=True)
        expected = evaluate_predictions(trained.model, trained.metadata, training_data)
        actual = evaluate_model(paths, data=training_data)
        pd.testing.assert_frame_equal(expected, actual)
        pd.testing.assert_frame_equal(before, training_data)
        output = tmp_path.joinpath("predictions", "test.csv")
        save_predictions(actual, output)
        assert len(pd.read_csv(output)) == len(actual)
        columns = list(NUMERIC_FEATURES + CATEGORICAL_FEATURES)
        np.testing.assert_array_equal(
            model.predict(training_data[columns]),
            trained.model.predict(training_data[columns]),
        )

    def test_metadata_property_returns_snapshot(self, trained):
        metadata = trained.metadata
        metadata["numeric_features"].clear()
        assert trained.metadata["numeric_features"] == list(NUMERIC_FEATURES)

    def test_invalid_metadata_does_not_write_artifacts(self, trained, paths):
        with pytest.raises(ValueError):
            save_model(
                trained.model,
                {**trained.metadata, "contract_features_used": True},
                paths,
            )
        assert not paths.model.exists()
        assert not paths.metadata.exists()

    @pytest.fixture(
        params=[
            pytest.param("order", id="feature-order"),
            pytest.param("boolean-rows", id="boolean-rows"),
            pytest.param("string-year", id="string-year"),
            pytest.param("unknown", id="unexpected-field"),
        ]
    )
    def malformed_metadata(self, request):
        metadata = json.loads(
            files("ml")
            .joinpath("resources/skater_value_model_metadata.json")
            .read_text()
        )
        if request.param == "order":
            metadata["numeric_features"].reverse()
        if request.param == "boolean-rows":
            metadata["metrics"]["test"]["rows"] = True
        if request.param == "string-year":
            metadata["test_target_season"] = "2025"
        if request.param == "unknown":
            metadata["unexpected"] = True
        return metadata

    def test_metadata_schema_rejects_malformed_inputs(self, malformed_metadata):
        with pytest.raises(ValueError):
            validate_metadata(malformed_metadata)

    @pytest.fixture(
        params=[
            pytest.param(np.ones((20, 1)), id="matrix"),
            pytest.param(np.array(1.0), id="scalar"),
            pytest.param(np.full(20, np.inf), id="infinite"),
        ]
    )
    def invalid_predictions(self, request):
        return request.param

    def test_prediction_schema_rejects_invalid_shape_and_values(
        self, player_seasons, invalid_predictions
    ):
        with pytest.raises(ValueError):
            prediction_frame(
                player_seasons.assign(target_season=player_seasons["season"] + 1),
                invalid_predictions,
            )

    def test_missing_target_seasons_are_rejected(self, training_data):
        with pytest.raises(ValueError, match="whole years"):
            temporal_splits(training_data.assign(target_season=np.nan))

"""Behavior at ML data, configuration, and artifact boundaries."""

import json
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from importlib.resources import files
from ml.tests.fakes import PipelineResources, ReadScenario, DatasetScenario, FrameReader
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
from ml.evaluation.gate import (
    build_prediction_frame,
    split_temporal_data,
    validate_metadata,
)
from ml.features.build_features import build_features
from ml.features.replacement_level import calculate_replacement_level
from ml.pipelines.build_model_dataset import build_model_dataset
from ml.pipelines.run_pipeline import run_pipeline
from ml.pipelines import repository as pipeline_repository
from ml.pipelines.repository import ModelDataReader
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
        module = pipeline_repository
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
        monkeypatch.setattr(module, "open_database_resources", resources)
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
        self, player_seasons, caps, counted_reads, original_frames
    ):
        result = run_pipeline(players=player_seasons, salary_caps=caps)
        assert counted_reads.calls == []
        assert len(result) == len(player_seasons)
        pd.testing.assert_frame_equal(original_frames.players, player_seasons)
        pd.testing.assert_frame_equal(original_frames.caps, caps)

    @pytest.fixture
    def reader(self, player_seasons, caps):
        return FrameReader(frames=DatasetScenario(players=player_seasons, caps=caps))

    def test_borrowed_reader_loads_inputs_without_acquiring_default_resources(
        self, reader, counted_reads, original_frames
    ):
        assert len(reader) == 0
        assert isinstance(reader, ModelDataReader)
        result = run_pipeline(reader=reader)
        assert len(result) == 20
        assert reader.reads == ["players", "caps"]
        assert counted_reads.calls == []
        pd.testing.assert_frame_equal(reader.frames.players, original_frames.players)
        pd.testing.assert_frame_equal(reader.frames.caps, original_frames.caps)

    def test_preloaded_frames_do_not_read_from_a_borrowed_reader(
        self, reader, counted_reads, player_seasons, caps
    ):
        result = run_pipeline(players=player_seasons, salary_caps=caps, reader=reader)
        assert len(result) == 20
        assert reader.reads == []
        assert counted_reads.calls == []

    @pytest.fixture
    def original_frames(self, player_seasons, caps):
        return DatasetScenario(
            players=player_seasons.copy(deep=True), caps=caps.copy(deep=True)
        )

    def test_stage_computation_does_not_mutate_input(
        self, player_seasons, original_frames
    ):
        calculate_replacement_level(player_seasons)
        build_training_data(player_seasons)
        pd.testing.assert_frame_equal(original_frames.players, player_seasons)

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

    @pytest.fixture
    def model_options(self):
        return ModelOptions()

    def test_options_are_immutable_and_defaults_preserve_model(self, model_options):
        with pytest.raises(FrozenInstanceError):
            setattr(model_options, "random_state", 7)
        model = build_model()
        regressor = model.named_steps["model"]
        assert (
            regressor.learning_rate,
            regressor.max_iter,
            regressor.max_leaf_nodes,
            regressor.l2_regularization,
            regressor.random_state,
        ) == (0.05, 300, 31, 1.0, 42)

    @pytest.fixture
    def eligibility_options(self):
        return FeatureOptions(minimum_training_games=27)

    def test_training_eligibility_can_be_injected(
        self, player_seasons, eligibility_options
    ):
        result = build_features(player_seasons, options=eligibility_options)
        assert not result["eligible_for_training"].any()


class TestArtifacts:
    columns = NUMERIC_FEATURES + CATEGORICAL_FEATURES

    @pytest.fixture
    def training_options(self):
        return ModelOptions(max_iter=5)

    @pytest.fixture
    def training_data(self, player_seasons):
        return build_training_data(player_seasons)

    @pytest.fixture
    def trained(self, training_data, training_options):
        return train_model(training_data, options=training_options)

    @pytest.fixture
    def original_training_data(self, training_data):
        return training_data.copy(deep=True)

    @pytest.fixture
    def prediction_output(self, tmp_path):
        return tmp_path.joinpath("predictions", "test.csv")

    @pytest.fixture
    def invalid_metadata(self, trained):
        return {**trained.metadata, "contract_features_used": True}

    @pytest.fixture
    def working_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        return tmp_path

    @pytest.fixture
    def paths(self, tmp_path):
        return ArtifactPaths(
            model=tmp_path.joinpath("models", "model.joblib"),
            metadata=tmp_path.joinpath("metadata", "model.json"),
        )

    def test_training_is_silent_and_has_no_artifact_side_effects(
        self, player_seasons, working_directory, training_options, capsys
    ):
        train(player_seasons, options=training_options)
        assert list(working_directory.iterdir()) == []
        assert capsys.readouterr().out == ""

    def test_explicit_artifacts_round_trip_and_evaluation_owns_data(
        self, trained, training_data, paths, original_training_data, prediction_output
    ):
        save_model(trained.model, trained.metadata, paths)
        model, metadata = load_model(paths)
        assert metadata == trained.metadata_value
        assert paths.metadata.read_text() == trained.metadata_json
        expected = evaluate_predictions(trained.model, trained.metadata, training_data)
        actual = evaluate_model(paths, data=training_data)
        pd.testing.assert_frame_equal(expected, actual)
        pd.testing.assert_frame_equal(original_training_data, training_data)
        save_predictions(actual, prediction_output)
        assert len(pd.read_csv(prediction_output)) == len(actual)
        np.testing.assert_array_equal(
            model.predict(training_data[list(self.columns)]),
            trained.model.predict(training_data[list(self.columns)]),
        )

    def test_metadata_property_returns_snapshot(self, trained):
        metadata = trained.metadata
        metadata["numeric_features"].clear()
        metadata["metrics"].clear()
        assert trained.metadata["numeric_features"] == list(NUMERIC_FEATURES)
        assert set(trained.metadata["metrics"]) == {"train", "validation", "test"}

    def test_invalid_metadata_does_not_write_artifacts(
        self, trained, paths, invalid_metadata
    ):
        with pytest.raises(ValueError):
            save_model(
                trained.model,
                invalid_metadata,
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
            pytest.param("matrix", id="matrix"),
            pytest.param("scalar", id="scalar"),
            pytest.param("infinite", id="infinite"),
        ]
    )
    def invalid_predictions(self, request):
        if request.param == "matrix":
            return np.ones((20, 1))
        if request.param == "scalar":
            return np.array(1.0)
        return np.full(20, np.inf)

    @pytest.fixture
    def prediction_source(self, player_seasons):
        return player_seasons.assign(target_season=player_seasons["season"] + 1)

    def test_prediction_schema_rejects_invalid_shape_and_values(
        self, prediction_source, invalid_predictions
    ):
        with pytest.raises(ValueError):
            build_prediction_frame(
                prediction_source,
                invalid_predictions,
            )

    @pytest.fixture
    def missing_target(self, training_data):
        return training_data.assign(target_season=np.nan)

    def test_missing_target_seasons_are_rejected(self, missing_target):
        with pytest.raises(ValueError, match="whole years"):
            split_temporal_data(missing_target)

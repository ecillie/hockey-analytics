"""Correlated aggregate ML diagnostics preserve training and artifact behavior."""

from io import StringIO
import json
import logging

import numpy as np
import pandas as pd
import pytest

from app.shared.observability.domain import (
    InvocationContext,
    LogFormat,
    LogLevel,
    LoggingSettings,
)
from app.shared.observability.sinks import build_diagnostic_handler
from ml.artifacts import ArtifactPaths, save_model
from ml.configuration import CATEGORICAL_FEATURES, NUMERIC_FEATURES, ModelOptions
from ml.evaluation.evaluate_skater_model import evaluate_model
from ml.training.train_skater_value import (
    build_training_data,
    train_model,
    train_skater_model,
)


class TestMlLogging:
    @pytest.fixture(
        params=[pytest.param(format, id=format.value) for format in LogFormat]
    )
    def format(self, request):
        return request.param

    @pytest.fixture(
        params=[
            pytest.param(level, id=level.name)
            for level in (LogLevel.INFO, LogLevel.DEBUG)
        ]
    )
    def level(self, request):
        return request.param

    @pytest.fixture
    def capture(self, format, level, monkeypatch):
        output = StringIO()
        handler = build_diagnostic_handler(
            LoggingSettings(format=format, level=level), output
        )
        target = logging.getLogger("ml.observability")
        monkeypatch.setattr(target, "handlers", [handler])
        monkeypatch.setattr(target, "level", logging.DEBUG)
        monkeypatch.setattr(target, "propagate", False)
        yield output
        handler.close()

    @pytest.fixture
    def context(self):
        return InvocationContext(
            invocation_id="generated-invocation", source="ml.probe", started_ns=0
        )

    @pytest.fixture
    def source(self, player_seasons):
        return player_seasons.assign(
            player_name="payload_secret", private_payload="private_secret"
        )

    @pytest.fixture
    def training_data(self, source):
        return build_training_data(source)

    @pytest.fixture
    def original(self, training_data):
        return training_data.copy(deep=True)

    @pytest.fixture
    def options(self):
        return ModelOptions(max_iter=5)

    @pytest.fixture
    def baseline(self, training_data, options):
        return train_model(training_data, options=options)

    @pytest.fixture
    def paths(self, tmp_path):
        return ArtifactPaths(
            model=tmp_path.joinpath("path_secret", "model.joblib"),
            metadata=tmp_path.joinpath("path_secret", "model.json"),
        )

    @pytest.fixture
    def predictions_path(self, tmp_path):
        return tmp_path.joinpath("path_secret", "predictions.csv")

    @pytest.fixture
    def trained(self, capture, source, paths, options, context):
        return train_skater_model(source, paths=paths, options=options, context=context)

    @pytest.fixture
    def evaluated(self, trained, paths, training_data, predictions_path, context):
        return evaluate_model(
            paths, data=training_data, output=predictions_path, context=context
        )

    @pytest.fixture
    def training_features(self, training_data):
        return training_data[list(NUMERIC_FEATURES + CATEGORICAL_FEATURES)]

    def test_diagnostics_preserve_outputs_and_exclude_payloads(
        self,
        evaluated,
        trained,
        baseline,
        original,
        training_data,
        training_features,
        capture,
        level,
        paths,
        predictions_path,
    ):
        pd.testing.assert_frame_equal(original, training_data)
        np.testing.assert_array_equal(
            trained.predict(training_features),
            baseline.model.predict(training_features),
        )
        assert paths.metadata.read_text() == baseline.metadata_json
        assert len(pd.read_csv(predictions_path)) == len(evaluated)
        events = [
            json.loads(line.removeprefix("event "))
            for line in capture.getvalue().splitlines()
        ]
        assert {item["invocation_id"] for item in events} == {"generated-invocation"}
        assert {item["source"] for item in events} == {"ml.probe"}
        splits = [item for item in events if item["event"] == "ml.split_ready"]
        assert len(splits) == (3 if level is LogLevel.DEBUG else 0)
        metrics = [item for item in events if item["event"] == "ml.split_evaluated"]
        assert len(metrics) == 3
        assert all({"rows", "mae", "rmse", "r2"} <= item.keys() for item in metrics)
        assert [
            item["stage"] for item in events if item["event"] == "ml.artifact_written"
        ] == ["model", "metadata", "predictions"]
        assert sum(item["event"] == "ml.training_finished" for item in events) == 1
        assert sum(item["event"] == "ml.evaluation_finished" for item in events) == 1
        assert "secret" not in capture.getvalue()
        assert all(
            len(line.encode()) < 8192 for line in capture.getvalue().splitlines()
        )

    @pytest.fixture
    def invalid_paths(self, tmp_path):
        return ArtifactPaths(model=tmp_path.joinpath("model.joblib"), metadata=tmp_path)

    def test_partial_artifact_failure_reports_only_completed_write(
        self, capture, baseline, invalid_paths, context
    ):
        with pytest.raises(IsADirectoryError):
            save_model(
                baseline.model, baseline.metadata_value, invalid_paths, context=context
            )
        events = [
            json.loads(line.removeprefix("event "))
            for line in capture.getvalue().splitlines()
        ]
        assert [(item["event"], item["stage"]) for item in events] == [
            ("ml.artifact_written", "model")
        ]
        assert invalid_paths.model.is_file()

    def test_library_training_remains_silent_without_context(self, capture, baseline):
        assert baseline.metadata_value.metrics.train.rows > 0
        assert capture.getvalue() == ""

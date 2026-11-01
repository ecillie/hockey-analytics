"""Prediction evaluation with explicit model and artifact boundaries."""

import numpy as np
import pandas as pd
from pathlib import Path
from numpy.typing import ArrayLike
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline

from app.shared.observability.domain import InvocationContext
from ml.domain import (
    ArtifactPaths,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    MetricValues,
)
from ml.evaluation.util import build_prediction_frame, validate_metadata
from ml.repository import load_model, save_predictions
from ml.schemas import validate_frame
from ml.errors import EvaluationRowsError
from ml.training.services import build_training_data
from ml.observability.services import report_ml_progress


def calculate_prediction_metrics(
    actual: ArrayLike, predicted: ArrayLike
) -> MetricValues:
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
        "r2": float(r2_score(actual, predicted)),
    }


def evaluate_predictions(
    model: Pipeline, metadata: object, data: pd.DataFrame
) -> pd.DataFrame:
    parsed = validate_metadata(metadata)
    validate_frame(
        data,
        required=(
            "player_id",
            "season",
            "target_season",
            "current_hockey_value",
            "next_season_hockey_value",
            *NUMERIC_FEATURES,
            *CATEGORICAL_FEATURES,
        ),
        grain=("player_id", "season"),
    )
    test_season = parsed.test_target_season
    result = data[data["target_season"] == test_season].copy()
    if result.empty:
        raise EvaluationRowsError(season=test_season)
    predictions = np.asarray(
        model.predict(result[list(NUMERIC_FEATURES + CATEGORICAL_FEATURES)])
    )
    build_prediction_frame(result, predictions)
    result["ml_prediction"] = predictions
    result["naive_prediction"] = result["current_hockey_value"]
    result["prediction_error"] = predictions - result["next_season_hockey_value"]
    result["absolute_error"] = result["prediction_error"].abs()
    result["ml_absolute_error"] = result["absolute_error"]
    result["naive_absolute_error"] = (
        result["naive_prediction"] - result["next_season_hockey_value"]
    ).abs()
    result["improvement_vs_naive"] = (
        result["naive_absolute_error"] - result["ml_absolute_error"]
    )
    result["prediction_tier"] = pd.qcut(
        result["ml_prediction"], q=5, labels=False, duplicates="drop"
    )
    return result


def evaluate_model(
    paths: ArtifactPaths,
    *,
    data: pd.DataFrame | None = None,
    output: Path | None = None,
    context: InvocationContext | None = None,
) -> pd.DataFrame:
    model, metadata = load_model(paths, context=context)
    selected = build_training_data() if data is None else data
    report_ml_progress(
        context,
        event="ml.dataset_ready",
        stage="evaluation",
        values={"rows": len(selected)},
    )
    result = evaluate_predictions(model, metadata, selected)
    if context is not None:
        values = calculate_prediction_metrics(
            result["next_season_hockey_value"], result["ml_prediction"]
        )
        report_ml_progress(
            context,
            event="ml.evaluation_finished",
            stage="test",
            values=values | {"rows": len(result)},
        )
    if output is not None:
        save_predictions(result, output, context=context)
    return result

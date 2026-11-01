"""Model evaluation over an owned dataset with explicit artifact adapters."""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd
from app.shared.cli import ExitCode
from app.config import load_environment
from app.shared.observability.domain import (
    CommandOutcome,
    InvocationContext,
    read_logging_settings,
)
from app.shared.observability.errors import LoggingSettingsError
from app.shared.observability.services import (
    configure_logging,
    start_command,
    configure_command_exceptions,
    finish_command,
)
from numpy.typing import ArrayLike
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline

from ml.artifacts import ArtifactPaths, load_model, save_predictions
from ml.configuration import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from ml.evaluation.gate import build_prediction_frame, validate_metadata
from ml.paths import resolve_artifact_directory
from ml.schemas import validate_frame
from ml.errors import EvaluationRowsError
from ml.observability.services import report_ml_progress
from ml.training.train_skater_value import build_training_data


def calculate_prediction_metrics(
    actual: ArrayLike, predicted: ArrayLike
) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
        "r2": float(r2_score(actual, predicted)),
    }


metrics = calculate_prediction_metrics


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


def print_metrics(label: str, values: dict[str, float]) -> None:
    print(f"\n{label}")
    print(
        f"MAE: {values['mae']:.4f}\nRMSE: {values['rmse']:.4f}\nR²: {values['r2']:.4f}"
    )


def print_evaluation_diagnostics(data: pd.DataFrame) -> None:
    actual = data["next_season_hockey_value"]
    print_metrics(
        "ML MODEL", calculate_prediction_metrics(actual, data["ml_prediction"])
    )
    print_metrics(
        "NAIVE CURRENT-VALUE BENCHMARK",
        calculate_prediction_metrics(actual, data["naive_prediction"]),
    )
    for position, group in data.groupby("position_group"):
        print_metrics(
            str(position),
            calculate_prediction_metrics(
                group["next_season_hockey_value"], group["ml_prediction"]
            ),
        )
    calibration = data.groupby("prediction_tier", observed=True).agg(
        players=("player_id", "count"),
        avg_prediction=("ml_prediction", "mean"),
        avg_actual=("next_season_hockey_value", "mean"),
    )
    print(calibration.to_string())
    print(
        data.sort_values("absolute_error", ascending=False)
        .head(20)
        .to_string(index=False)
    )
    print(
        data.sort_values("improvement_vs_naive", ascending=False)
        .head(20)
        .to_string(index=False)
    )


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


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    try:
        settings = read_logging_settings(load_environment())
    except LoggingSettingsError as error:
        parser.error(str(error))
    configure_logging(settings)
    context = start_command("ml.evaluate_skater_model")
    configure_command_exceptions(context)
    try:
        execute_command(context=context)
    except Exception:
        logger.exception(
            "Command failed", extra=context.fields | {"event": "command.failed"}
        )
        finish_command(context, CommandOutcome.FAILED)
        return ExitCode.FAILURE
    finish_command(context, CommandOutcome.COMPLETED)
    return ExitCode.SUCCESS


def execute_command(*, context: InvocationContext | None = None) -> None:
    directory = resolve_artifact_directory("TRADEVALUE_MODEL_DIR", Path("models"))
    output = resolve_artifact_directory(
        "TRADEVALUE_EVALUATION_DIR", Path("evaluation/outputs")
    )
    paths = ArtifactPaths(
        model=directory.joinpath("skater_value_model.joblib"),
        metadata=directory.joinpath("skater_value_model_metadata.json"),
    )
    print_evaluation_diagnostics(
        evaluate_model(
            paths,
            output=output.joinpath("skater_model_test_predictions.csv"),
            context=context,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

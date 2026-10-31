"""Model evaluation over an owned dataset with explicit artifact adapters."""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd
from app.shared.cli import ExitCode
from numpy.typing import ArrayLike
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline

from ml.artifacts import ArtifactPaths, load_model, save_predictions
from ml.configuration import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from ml.evaluation.gate import prediction_frame, validate_metadata
from ml.paths import artifact_directory
from ml.schemas import validate_frame
from ml.training.train_skater_value import build_training_data


def metrics(actual: ArrayLike, predicted: ArrayLike) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
        "r2": float(r2_score(actual, predicted)),
    }


def evaluate_predictions(
    model: Pipeline, metadata: dict, data: pd.DataFrame
) -> pd.DataFrame:
    validate_metadata(metadata)
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
    test_season = metadata["test_target_season"]
    result = data[data["target_season"] == test_season].copy()
    if result.empty:
        raise ValueError(f"No rows found for test season {test_season}")
    predictions = np.asarray(
        model.predict(result[list(NUMERIC_FEATURES + CATEGORICAL_FEATURES)])
    )
    prediction_frame(result, predictions)
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
    print_metrics("ML MODEL", metrics(actual, data["ml_prediction"]))
    print_metrics(
        "NAIVE CURRENT-VALUE BENCHMARK", metrics(actual, data["naive_prediction"])
    )
    for position, group in data.groupby("position_group"):
        print_metrics(
            str(position),
            metrics(group["next_season_hockey_value"], group["ml_prediction"]),
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
) -> pd.DataFrame:
    model, metadata = load_model(paths)
    result = evaluate_predictions(
        model, metadata, build_training_data() if data is None else data
    )
    if output is not None:
        save_predictions(result, output)
    return result


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try:
        execute_command()
    except Exception:
        logger.exception("Command failed")
        return ExitCode.FAILURE
    return ExitCode.SUCCESS


def execute_command() -> None:
    directory = artifact_directory("TRADEVALUE_MODEL_DIR", Path("models"))
    output = artifact_directory("TRADEVALUE_EVALUATION_DIR", Path("evaluation/outputs"))
    paths = ArtifactPaths(
        model=directory.joinpath("skater_value_model.joblib"),
        metadata=directory.joinpath("skater_value_model_metadata.json"),
    )
    print_evaluation_diagnostics(
        evaluate_model(
            paths, output=output.joinpath("skater_model_test_predictions.csv")
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

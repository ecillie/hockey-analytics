"""Small, data-independent correctness gate for the skater value model."""

import argparse
import json
import logging
from collections.abc import Sequence
from importlib.resources import as_file, files
from pathlib import Path

import numpy as np
import pandas as pd
from app.shared.cli import ExitCode

from ml.configuration import CATEGORICAL_FEATURES, NUMERIC_FEATURES, MetricTolerance
from ml.schemas import ModelMetadata, validate_frame

PREDICTION_COLUMNS = ("player_id", "season", "prediction")
METRICS = ("mae", "rmse", "r2")
SPLITS = ("train", "validation", "test")


def temporal_splits(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if "target_season" not in df.columns:
        raise ValueError("target_season is required for temporal splits")
    if (
        df["target_season"].isna().any()
        or not np.isfinite(df["target_season"]).all()
        or (df["target_season"] % 1 != 0).any()
    ):
        raise ValueError("Target seasons must be finite whole years")
    seasons = sorted(df["target_season"].unique())
    if len(seasons) < 3:
        raise ValueError("At least three target seasons are required")
    validation_season, test_season = seasons[-2:]
    return {
        "train": df[df["target_season"] < validation_season].copy(),
        "validation": df[df["target_season"] == validation_season].copy(),
        "test": df[df["target_season"] == test_season].copy(),
    }


def prediction_frame(df: pd.DataFrame, predictions: np.ndarray) -> pd.DataFrame:
    validate_frame(
        df,
        required=("player_id", "target_season"),
        grain=("player_id", "target_season"),
    )
    values = np.asarray(predictions, dtype=float)
    if values.ndim != 1 or len(values) != len(df) or not np.isfinite(values).all():
        raise ValueError("Predictions must be finite and match the input rows")
    return pd.DataFrame(
        {
            "player_id": df["player_id"].to_numpy(),
            "season": df["target_season"].to_numpy(),
            "prediction": np.maximum(values, 0.0),
        }
    )[list(PREDICTION_COLUMNS)]


def validate_metadata(metadata: dict) -> None:
    parsed = ModelMetadata.model_validate(metadata)
    if metadata["contract_features_used"] is not False:
        raise ValueError("Contract features must not be used by the model")
    if tuple(metadata["numeric_features"]) != NUMERIC_FEATURES:
        raise ValueError("Metadata numeric feature list is out of sync")
    if tuple(metadata["categorical_features"]) != CATEGORICAL_FEATURES:
        raise ValueError("Metadata categorical feature list is out of sync")
    if not metadata["validation_target_season"] < metadata["test_target_season"]:
        raise ValueError("Validation must precede test")
    if set(metadata["metrics"]) != set(SPLITS):
        raise ValueError("Metadata must contain train, validation, and test metrics")
    if (
        parsed.model_type != "HistGradientBoostingRegressor"
        or parsed.target != "next_season_hockey_value"
    ):
        raise ValueError("Unsupported model type or target")


def check_metric_regression(
    current: dict[str, float],
    baseline: dict[str, float],
    tolerance: dict[str, float] | None = None,
) -> None:
    tolerance = MetricTolerance().values if tolerance is None else tolerance
    for metric in METRICS:
        if metric not in current or metric not in baseline or metric not in tolerance:
            raise ValueError(f"Missing metric: {metric}")
        if (
            not all(
                np.isfinite(value)
                for value in (current[metric], baseline[metric], tolerance[metric])
            )
            or tolerance[metric] < 0
        ):
            raise ValueError(f"Invalid metric or tolerance: {metric}")
        regression = (
            current[metric] - baseline[metric]
            if metric != "r2"
            else baseline[metric] - current[metric]
        )
        if regression > tolerance[metric]:
            raise AssertionError(
                f"{metric} regressed by {regression:.4f}; allowed {tolerance[metric]:.4f}"
            )


def validate_committed_model_metadata(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        metadata = json.load(handle)
    validate_metadata(metadata)
    return metadata


def stable_metadata_json(metadata: dict) -> str:
    validate_metadata(metadata)
    return json.dumps(metadata, indent=2, sort_keys=True) + "\n"


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
    with as_file(
        files("ml").joinpath("resources/skater_value_model_metadata.json")
    ) as path:
        metadata = validate_committed_model_metadata(path)

    limits = {
        "train": {"mae": 7.6307295257, "rmse": 10.3311876346, "r2": 0.6501067487},
        "validation": {"mae": 8.2497447023, "rmse": 11.3177165668, "r2": 0.6429673612},
        "test": {"mae": 9.3361370822, "rmse": 13.2279709137, "r2": 0.5664511622},
    }
    for split in SPLITS:
        check_metric_regression(
            metadata["metrics"][split],
            limits[split],
            {"mae": 0.0, "rmse": 0.0, "r2": 0.0},
        )
    print("ML correctness and metric gate passed")


if __name__ == "__main__":
    raise SystemExit(main())

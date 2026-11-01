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
import os
from app.shared.observability.domain import (
    CommandOutcome,
    InvocationContext,
    read_logging_settings,
)
from app.shared.observability.errors import LoggingSettingsError
from app.shared.observability.services import (
    configure_logging,
    start_command,
    finish_command,
)

from ml.configuration import MetricTolerance
from ml.schemas import ModelMetadata, validate_frame
from ml.domain import Metric, Split
from ml.errors import (
    MissingTargetSeasonError,
    InvalidTargetSeasonsError,
    InsufficientSeasonsError,
    PredictionValuesError,
    MissingMetricError,
    InvalidMetricError,
    MetricRegressionError,
)
from ml.policy import find_metadata_violation
from ml.observability.services import report_ml_progress

PREDICTION_COLUMNS = ("player_id", "season", "prediction")
METRICS = tuple(Metric)
SPLITS = tuple(Split)


def split_temporal_data(df: pd.DataFrame) -> dict[Split, pd.DataFrame]:
    if "target_season" not in df.columns:
        raise MissingTargetSeasonError(columns=tuple(df.columns))
    invalid = (
        df["target_season"].isna()
        | ~np.isfinite(df["target_season"])
        | (df["target_season"] % 1 != 0)
    )
    if invalid.any():
        raise InvalidTargetSeasonsError(invalid_rows=int(invalid.sum()))
    seasons = sorted(df["target_season"].unique())
    if len(seasons) < 3:
        raise InsufficientSeasonsError(seasons=tuple(map(int, seasons)))
    validation_season, test_season = seasons[-2:]
    return {
        Split.TRAIN: df[df["target_season"] < validation_season].copy(),
        Split.VALIDATION: df[df["target_season"] == validation_season].copy(),
        Split.TEST: df[df["target_season"] == test_season].copy(),
    }


def build_prediction_frame(df: pd.DataFrame, predictions: np.ndarray) -> pd.DataFrame:
    validate_frame(
        df,
        required=("player_id", "target_season"),
        grain=("player_id", "target_season"),
    )
    values = np.asarray(predictions, dtype=float)
    if values.ndim != 1 or len(values) != len(df) or not np.isfinite(values).all():
        raise PredictionValuesError(shape=values.shape, expected_rows=len(df))
    return pd.DataFrame(
        {
            "player_id": df["player_id"].to_numpy(),
            "season": df["target_season"].to_numpy(),
            "prediction": np.maximum(values, 0.0),
        }
    )[list(PREDICTION_COLUMNS)]


def validate_metadata(metadata: object) -> ModelMetadata:
    parsed = ModelMetadata.model_validate(metadata)
    if violation := find_metadata_violation(parsed):
        raise violation
    return parsed


def check_metric_regression(
    current: dict[str, float],
    baseline: dict[str, float],
    tolerance: dict[str, float] | None = None,
) -> None:
    tolerance = MetricTolerance().values if tolerance is None else tolerance
    for metric in METRICS:
        if metric not in current or metric not in baseline or metric not in tolerance:
            raise MissingMetricError(metric=metric)
        if (
            not all(
                np.isfinite(value)
                for value in (current[metric], baseline[metric], tolerance[metric])
            )
            or tolerance[metric] < 0
        ):
            raise InvalidMetricError(
                metric=metric,
                current=current[metric],
                baseline=baseline[metric],
                tolerance=tolerance[metric],
            )
        regression = (
            current[metric] - baseline[metric]
            if metric != "r2"
            else baseline[metric] - current[metric]
        )
        if regression > tolerance[metric]:
            raise MetricRegressionError(
                metric=metric, regression=regression, tolerance=tolerance[metric]
            )


def validate_committed_model_metadata(path: Path) -> ModelMetadata:
    with path.open(encoding="utf-8") as handle:
        metadata = json.load(handle)
    return validate_metadata(metadata)


def serialize_metadata_json(metadata: object) -> str:
    parsed = validate_metadata(metadata)
    return (
        json.dumps(
            parsed.model_dump(mode="json", exclude_unset=True), indent=2, sort_keys=True
        )
        + "\n"
    )


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    try:
        settings = read_logging_settings(os.environ)
    except LoggingSettingsError as error:
        parser.error(str(error))
    configure_logging(settings)
    context = start_command("ml.metric_gate")
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
    with as_file(
        files("ml").joinpath("resources/skater_value_model_metadata.json")
    ) as path:
        metadata = validate_committed_model_metadata(path)
    report_ml_progress(context, event="ml.metadata_validated", stage="committed_model")

    limits = {
        "train": {"mae": 7.6307295257, "rmse": 10.3311876346, "r2": 0.6501067487},
        "validation": {"mae": 8.2497447023, "rmse": 11.3177165668, "r2": 0.6429673612},
        "test": {"mae": 9.3361370822, "rmse": 13.2279709137, "r2": 0.5664511622},
    }
    for split in SPLITS:
        values = metadata.metrics.split_values(split)
        check_metric_regression(
            {metric: values.metric_value(metric) for metric in METRICS},
            limits[split],
            {"mae": 0.0, "rmse": 0.0, "r2": 0.0},
        )
        report_ml_progress(
            context,
            event="ml.metric_gate_passed",
            stage=split.value,
            values={
                "rows": values.rows,
                "mae": values.mae,
                "rmse": values.rmse,
                "r2": values.r2,
            },
        )
    print("ML correctness and metric gate passed")


temporal_splits = split_temporal_data
prediction_frame = build_prediction_frame
stable_metadata_json = serialize_metadata_json

if __name__ == "__main__":
    raise SystemExit(main())

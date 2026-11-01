"""Pure temporal, prediction, metric and metadata boundary helpers."""

import json

import numpy as np
import pandas as pd

from ml.domain import MetricTolerance
from ml.schemas import ModelMetadata, validate_frame
from ml.domain import Metric, Split, MetricValues
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

PREDICTION_COLUMNS = ("player_id", "season", "prediction")
METRICS = tuple(Metric)


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
    current: MetricValues,
    baseline: MetricValues,
    tolerance: MetricValues | None = None,
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


def serialize_metadata_json(metadata: object) -> str:
    parsed = validate_metadata(metadata)
    return (
        json.dumps(
            parsed.model_dump(mode="json", exclude_unset=True), indent=2, sort_keys=True
        )
        + "\n"
    )

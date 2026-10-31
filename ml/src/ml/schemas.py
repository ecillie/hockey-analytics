"""Validation of external model metadata and dataframe boundaries."""

from typing import Annotated

import numpy as np
import pandas as pd
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    StrictBool,
    StrictInt,
)

from ml.configuration import FeatureOptions
from ml.errors import FrameColumnsError, FrameGrainError, FrameValuesError

type RowCount = Annotated[StrictInt, Field(gt=0)]


class SplitMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rows: RowCount
    mae: FiniteFloat
    rmse: FiniteFloat
    r2: FiniteFloat


class ModelMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    model_type: str
    target: str
    target_definition: str | None = None
    contract_features_used: StrictBool
    numeric_features: tuple[str, ...]
    categorical_features: tuple[str, ...]
    validation_target_season: StrictInt
    test_target_season: StrictInt
    metrics: dict[str, SplitMetrics]


def validate_frame(
    frame: pd.DataFrame,
    *,
    required: tuple[str, ...],
    grain: tuple[str, ...],
) -> None:
    missing = tuple(column for column in required if column not in frame.columns)
    if len(missing) > 0:
        raise FrameColumnsError(missing=missing)
    if frame.columns.duplicated().any():
        raise FrameGrainError(grain=grain)
    if frame[list(grain)].isna().any().any() or frame.duplicated(list(grain)).any():
        raise FrameGrainError(grain=grain)
    numbers = frame.select_dtypes("number")
    infinite = tuple(column for column in numbers if np.isinf(numbers[column]).any())
    if len(infinite) > 0:
        raise FrameValuesError(columns=infinite)


def validate_feature_options(options: FeatureOptions) -> None:
    if options.minimum_training_games < 1:
        raise ValueError("minimum_training_games must be positive")
    if not 0 <= options.replacement_percentile <= 1:
        raise ValueError("replacement_percentile must be between zero and one")
    if (
        not np.isfinite(options.salary_cap_normalization_dollars)
        or options.salary_cap_normalization_dollars <= 0
    ):
        raise ValueError("salary_cap_normalization_dollars must be finite and positive")

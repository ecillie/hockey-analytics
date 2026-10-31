"""Structured failures at ML data, metadata, and artifact boundaries."""

from typing import Literal

from ml.domain import Metric

type MinimumGamesField = Literal["min_games", "minimum_training_games"]
type FeatureKind = Literal["numeric", "categorical"]


class FrameColumnsError(ValueError):
    def __init__(self, *, missing: tuple[str, ...]) -> None:
        self.missing = missing
        super().__init__(f"Missing frame columns: {missing}")


class FrameGrainError(RuntimeError):
    def __init__(self, *, grain: tuple[str, ...]) -> None:
        self.grain = grain
        super().__init__(f"Frame contains duplicate or missing keys at grain {grain}")


class FrameValuesError(ValueError):
    def __init__(self, *, columns: tuple[str, ...]) -> None:
        self.columns = columns
        super().__init__(f"Non-finite frame values in {columns}")


class ContractFeaturesError(ValueError):
    def __init__(self, *, actual: bool) -> None:
        self.actual = actual
        super().__init__("Contract features must not be used by the model")


class FeatureOrderError(ValueError):
    def __init__(
        self,
        *,
        feature_kind: FeatureKind,
        actual: tuple[str, ...],
        expected: tuple[str, ...],
    ) -> None:
        self.feature_kind = feature_kind
        self.actual = actual
        self.expected = expected
        super().__init__(f"Metadata {feature_kind} feature list is out of sync")


class SplitOrderError(ValueError):
    def __init__(self, *, validation_season: int, test_season: int) -> None:
        self.validation_season = validation_season
        self.test_season = test_season
        super().__init__("Validation must precede test")


class ModelIdentityError(ValueError):
    def __init__(self, *, model_type: str, target: str) -> None:
        self.model_type = model_type
        self.target = target
        super().__init__(f"Unsupported model type or target: {model_type}, {target}")


class MissingTargetSeasonError(ValueError):
    def __init__(self, *, columns: tuple[str, ...]) -> None:
        self.columns = columns
        super().__init__("target_season is required for temporal splits")


class InvalidTargetSeasonsError(ValueError):
    def __init__(self, *, invalid_rows: int) -> None:
        self.invalid_rows = invalid_rows
        super().__init__("Target seasons must be finite whole years")


class InsufficientSeasonsError(ValueError):
    def __init__(self, *, seasons: tuple[int, ...]) -> None:
        self.seasons = seasons
        super().__init__("At least three target seasons are required")


class PredictionValuesError(ValueError):
    def __init__(self, *, shape: tuple[int, ...], expected_rows: int) -> None:
        self.shape = shape
        self.expected_rows = expected_rows
        super().__init__(
            f"Predictions must be finite and match {expected_rows} input rows; shape={shape}"
        )


class MissingMetricError(ValueError):
    def __init__(self, *, metric: Metric) -> None:
        self.metric = metric
        super().__init__(f"Missing metric: {metric}")


class InvalidMetricError(ValueError):
    def __init__(
        self, *, metric: Metric, current: float, baseline: float, tolerance: float
    ) -> None:
        self.metric = metric
        self.current = current
        self.baseline = baseline
        self.tolerance = tolerance
        super().__init__(f"Invalid metric or tolerance: {metric}")


class MetricRegressionError(AssertionError):
    def __init__(self, *, metric: Metric, regression: float, tolerance: float) -> None:
        self.metric = metric
        self.regression = regression
        self.tolerance = tolerance
        super().__init__(
            f"{metric} regressed by {regression:.4f}; allowed {tolerance:.4f}"
        )


class MinimumGamesError(ValueError):
    def __init__(self, *, field: MinimumGamesField, value: int) -> None:
        self.field = field
        self.value = value
        super().__init__(f"{field} must be positive; received {value}")


class ReplacementPercentileError(ValueError):
    def __init__(self, *, value: float) -> None:
        self.value = value
        super().__init__(
            f"replacement_percentile must be between zero and one; received {value}"
        )


class SalaryCapNormalizationError(ValueError):
    def __init__(self, *, value: float) -> None:
        self.value = value
        super().__init__(
            f"salary_cap_normalization_dollars must be finite and positive; received {value}"
        )


class TrainingRowsError(ValueError):
    def __init__(self, *, rows: int) -> None:
        self.rows = rows
        super().__init__("Training requires player-season rows")


class TrainingTargetsError(ValueError):
    def __init__(self, *, invalid_rows: int) -> None:
        self.invalid_rows = invalid_rows
        super().__init__(
            f"Training targets must be finite; invalid rows={invalid_rows}"
        )


class EvaluationRowsError(ValueError):
    def __init__(self, *, season: int) -> None:
        self.season = season
        super().__init__(f"No rows found for test season {season}")


class ModelArtifactError(TypeError):
    def __init__(self, *, actual_type: type) -> None:
        self.actual_type = actual_type
        super().__init__(
            f"Model artifact must contain an sklearn Pipeline; received {actual_type.__name__}"
        )


class ContractLeakageError(RuntimeError):
    def __init__(self, *, columns: tuple[str, ...]) -> None:
        self.columns = columns
        super().__init__(f"Contract data leaked into model dataset: {list(columns)}")

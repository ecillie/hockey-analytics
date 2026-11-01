"""Compatibility invariants for validated model metadata."""

from dataclasses import dataclass

from ml.configuration import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from ml.errors import (
    ContractFeaturesError,
    FeatureKind,
    FeatureOrderError,
    ModelIdentityError,
    SplitOrderError,
)
from ml.schemas import ModelMetadata


@dataclass(slots=True, kw_only=True, frozen=True)
class FeatureOrderPolicy:
    feature_kind: FeatureKind
    expected: tuple[str, ...]

    def find_violation(self, actual: tuple[str, ...]) -> FeatureOrderError | None:
        if actual != self.expected:
            return FeatureOrderError(
                feature_kind=self.feature_kind, actual=actual, expected=self.expected
            )
        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class ModelIdentityPolicy:
    model_type: str = "HistGradientBoostingRegressor"
    target: str = "next_season_hockey_value"

    def find_violation(self, metadata: ModelMetadata) -> ModelIdentityError | None:
        if (metadata.model_type, metadata.target) != (self.model_type, self.target):
            return ModelIdentityError(
                model_type=metadata.model_type, target=metadata.target
            )
        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class SplitOrderPolicy:
    validation_season: int

    def find_violation(self, test_season: int) -> SplitOrderError | None:
        if self.validation_season >= test_season:
            return SplitOrderError(
                validation_season=self.validation_season, test_season=test_season
            )
        return None


type MetadataViolation = (
    ContractFeaturesError | FeatureOrderError | ModelIdentityError | SplitOrderError
)


def find_metadata_violation(metadata: ModelMetadata) -> MetadataViolation | None:
    if metadata.contract_features_used:
        return ContractFeaturesError(actual=metadata.contract_features_used)
    if violation := FeatureOrderPolicy(
        feature_kind="numeric", expected=NUMERIC_FEATURES
    ).find_violation(metadata.numeric_features):
        return violation
    if violation := FeatureOrderPolicy(
        feature_kind="categorical", expected=CATEGORICAL_FEATURES
    ).find_violation(metadata.categorical_features):
        return violation
    if violation := SplitOrderPolicy(
        validation_season=metadata.validation_target_season
    ).find_violation(metadata.test_target_season):
        return violation
    return ModelIdentityPolicy().find_violation(metadata)

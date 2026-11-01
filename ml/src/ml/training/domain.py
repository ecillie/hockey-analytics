"""A fitted model handle with immutable validated metadata."""

from dataclasses import dataclass
from sklearn.pipeline import Pipeline
from ml.schemas import ModelMetadata
from ml.evaluation.util import serialize_metadata_json


@dataclass(slots=True, kw_only=True, frozen=True)
class TrainingResult:
    model: Pipeline
    metadata_value: ModelMetadata

    @property
    def metadata(self) -> dict[str, object]:
        return self.metadata_value.model_dump(mode="json", exclude_unset=True)

    @property
    def metadata_json(self) -> str:
        return serialize_metadata_json(self.metadata_value)

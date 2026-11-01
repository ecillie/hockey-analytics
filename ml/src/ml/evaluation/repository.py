"""Read validated model metadata from an explicitly selected path."""

import json
from pathlib import Path
from ml.schemas import ModelMetadata
from ml.evaluation.util import validate_metadata


def validate_committed_model_metadata(path: Path) -> ModelMetadata:
    with path.open(encoding="utf-8") as handle:
        metadata = json.load(handle)
    return validate_metadata(metadata)

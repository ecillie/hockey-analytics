"""Explicit model, metadata, and prediction persistence."""

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd
from sklearn.pipeline import Pipeline

from ml.evaluation.gate import stable_metadata_json, validate_metadata
from ml.schemas import ModelMetadata
from ml.errors import ModelArtifactError


@dataclass(slots=True, kw_only=True, frozen=True)
class ArtifactPaths:
    model: Path
    metadata: Path


def save_model(model: Pipeline, metadata: object, paths: ArtifactPaths) -> None:
    serialized = stable_metadata_json(metadata)
    paths.model.parent.mkdir(parents=True, exist_ok=True)
    paths.metadata.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, paths.model)
    paths.metadata.write_text(serialized, encoding="utf-8")


def load_model(paths: ArtifactPaths) -> tuple[Pipeline, ModelMetadata]:
    metadata = json.loads(paths.metadata.read_text(encoding="utf-8"))
    metadata = validate_metadata(metadata)
    model = joblib.load(paths.model)
    if not isinstance(model, Pipeline):
        raise ModelArtifactError(actual_type=type(model))
    return model, metadata


def save_predictions(predictions: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(path, index=False)

"""Explicit model, metadata, and prediction persistence."""

import json
from pathlib import Path
from ml.domain import ArtifactPaths

import joblib
import pandas as pd
from sklearn.pipeline import Pipeline

from ml.evaluation.util import serialize_metadata_json, validate_metadata
from ml.schemas import ModelMetadata
from ml.errors import ModelArtifactError
from app.shared.observability.domain import InvocationContext
from ml.observability.services import report_ml_progress


def save_model(
    model: Pipeline,
    metadata: object,
    paths: ArtifactPaths,
    *,
    context: InvocationContext | None = None,
) -> None:
    serialized = serialize_metadata_json(metadata)
    paths.model.parent.mkdir(parents=True, exist_ok=True)
    paths.metadata.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, paths.model)
    report_ml_progress(context, event="ml.artifact_written", stage="model")
    paths.metadata.write_text(serialized, encoding="utf-8")
    report_ml_progress(context, event="ml.artifact_written", stage="metadata")


def load_model(
    paths: ArtifactPaths, *, context: InvocationContext | None = None
) -> tuple[Pipeline, ModelMetadata]:
    metadata = json.loads(paths.metadata.read_text(encoding="utf-8"))
    metadata = validate_metadata(metadata)
    model = joblib.load(paths.model)
    if not isinstance(model, Pipeline):
        raise ModelArtifactError(actual_type=type(model))
    report_ml_progress(context, event="ml.artifact_loaded", stage="model_bundle")
    return model, metadata


def save_predictions(
    predictions: pd.DataFrame, path: Path, *, context: InvocationContext | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(path, index=False)
    report_ml_progress(
        context,
        event="ml.artifact_written",
        stage="predictions",
        values={"rows": len(predictions)},
    )

"""Compatibility exports for model artifact paths and persistence."""

from ml.domain import (
    ArtifactPaths as ArtifactPaths,
)
from ml.repository import (
    load_model as load_model,
    save_model as save_model,
    save_predictions as save_predictions,
)

"""Skater training command and public compatibility exports."""

from ml.training.services import (
    build_training_data as build_training_data,
    build_model as build_model,
    evaluate_training_split as evaluate_training_split,
    train_model as train_model,
    train_skater_model as train_skater_model,
)
from ml.training.domain import (
    TrainingResult as TrainingResult,
)
from ml.domain import (
    CATEGORICAL_FEATURES as CATEGORICAL_FEATURES,
    NUMERIC_FEATURES as NUMERIC_FEATURES,
)

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from app.shared.cli import ExitCode
from app.config import load_environment
from app.shared.observability.domain import (
    CommandOutcome,
    read_logging_settings,
)
from app.shared.observability.errors import LoggingSettingsError
from app.shared.observability.services import (
    configure_logging,
    start_command,
    configure_command_exceptions,
    finish_command,
)

from ml.artifacts import ArtifactPaths
from ml.paths import resolve_artifact_directory


evaluate = evaluate_training_split
train = train_skater_model


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="train skater value")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    try:
        settings = read_logging_settings(load_environment())
    except LoggingSettingsError as error:
        parser.error(str(error))
    configure_logging(settings)
    context = start_command("ml.train_skater_value")
    configure_command_exceptions(context)
    try:
        directory = resolve_artifact_directory("TRADEVALUE_MODEL_DIR", Path("models"))
        train_skater_model(
            context=context,
            paths=ArtifactPaths(
                model=directory.joinpath("skater_value_model.joblib"),
                metadata=directory.joinpath("skater_value_model_metadata.json"),
            ),
        )
    except Exception:
        logger.exception(
            "Command failed", extra=context.fields | {"event": "command.failed"}
        )
        finish_command(context, CommandOutcome.FAILED)
        return ExitCode.FAILURE
    finish_command(context, CommandOutcome.COMPLETED)
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())

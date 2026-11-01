"""Small, data-independent correctness gate for the skater value model."""

from ml.evaluation.util import (
    PREDICTION_COLUMNS as PREDICTION_COLUMNS,
    split_temporal_data as split_temporal_data,
    build_prediction_frame as build_prediction_frame,
    validate_metadata as validate_metadata,
    check_metric_regression as check_metric_regression,
    serialize_metadata_json as serialize_metadata_json,
)
from ml.evaluation.repository import (
    validate_committed_model_metadata as validate_committed_model_metadata,
)

import argparse
import logging
from collections.abc import Sequence
from importlib.resources import as_file, files

from app.shared.cli import ExitCode
import os
from app.shared.observability.domain import (
    CommandOutcome,
    InvocationContext,
    read_logging_settings,
)
from app.shared.observability.errors import LoggingSettingsError
from app.shared.observability.services import (
    configure_logging,
    start_command,
    configure_command_exceptions,
    finish_command,
)

from ml.domain import Metric, Split
from ml.observability.services import report_ml_progress

METRICS = tuple(Metric)
SPLITS = tuple(Split)


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    try:
        settings = read_logging_settings(os.environ)
    except LoggingSettingsError as error:
        parser.error(str(error))
    configure_logging(settings)
    context = start_command("ml.metric_gate")
    configure_command_exceptions(context)
    try:
        execute_command(context=context)
    except Exception:
        logger.exception(
            "Command failed", extra=context.fields | {"event": "command.failed"}
        )
        finish_command(context, CommandOutcome.FAILED)
        return ExitCode.FAILURE
    finish_command(context, CommandOutcome.COMPLETED)
    return ExitCode.SUCCESS


def execute_command(*, context: InvocationContext | None = None) -> None:
    with as_file(
        files("ml").joinpath("resources/skater_value_model_metadata.json")
    ) as path:
        metadata = validate_committed_model_metadata(path)
    report_ml_progress(context, event="ml.metadata_validated", stage="committed_model")

    limits = {
        "train": {"mae": 7.6307295257, "rmse": 10.3311876346, "r2": 0.6501067487},
        "validation": {"mae": 8.2497447023, "rmse": 11.3177165668, "r2": 0.6429673612},
        "test": {"mae": 9.3361370822, "rmse": 13.2279709137, "r2": 0.5664511622},
    }
    for split in SPLITS:
        values = metadata.metrics.split_values(split)
        check_metric_regression(
            {metric: values.metric_value(metric) for metric in METRICS},
            limits[split],
            {"mae": 0.0, "rmse": 0.0, "r2": 0.0},
        )
        report_ml_progress(
            context,
            event="ml.metric_gate_passed",
            stage=split.value,
            values={
                "rows": values.rows,
                "mae": values.mae,
                "rmse": values.rmse,
                "r2": values.r2,
            },
        )
    print("ML correctness and metric gate passed")


temporal_splits = split_temporal_data
prediction_frame = build_prediction_frame
stable_metadata_json = serialize_metadata_json

if __name__ == "__main__":
    raise SystemExit(main())

"""Model evaluation over an owned dataset with explicit artifact adapters."""

from ml.evaluation.services import (
    calculate_prediction_metrics as calculate_prediction_metrics,
    evaluate_predictions as evaluate_predictions,
    evaluate_model as evaluate_model,
)

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

import pandas as pd
from app.shared.cli import ExitCode
from app.config import load_environment
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

from ml.artifacts import ArtifactPaths
from ml.paths import resolve_artifact_directory
from ml.domain import MetricValues

metrics = calculate_prediction_metrics


def print_metrics(label: str, values: MetricValues) -> None:
    print(f"\n{label}")
    print(
        f"MAE: {values['mae']:.4f}\nRMSE: {values['rmse']:.4f}\nR²: {values['r2']:.4f}"
    )


def print_evaluation_diagnostics(data: pd.DataFrame) -> None:
    actual = data["next_season_hockey_value"]
    print_metrics(
        "ML MODEL", calculate_prediction_metrics(actual, data["ml_prediction"])
    )
    print_metrics(
        "NAIVE CURRENT-VALUE BENCHMARK",
        calculate_prediction_metrics(actual, data["naive_prediction"]),
    )
    for position, group in data.groupby("position_group"):
        print_metrics(
            str(position),
            calculate_prediction_metrics(
                group["next_season_hockey_value"], group["ml_prediction"]
            ),
        )
    calibration = data.groupby("prediction_tier", observed=True).agg(
        players=("player_id", "count"),
        avg_prediction=("ml_prediction", "mean"),
        avg_actual=("next_season_hockey_value", "mean"),
    )
    print(calibration.to_string())
    print(
        data.sort_values("absolute_error", ascending=False)
        .head(20)
        .to_string(index=False)
    )
    print(
        data.sort_values("improvement_vs_naive", ascending=False)
        .head(20)
        .to_string(index=False)
    )


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    try:
        settings = read_logging_settings(load_environment())
    except LoggingSettingsError as error:
        parser.error(str(error))
    configure_logging(settings)
    context = start_command("ml.evaluate_skater_model")
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
    directory = resolve_artifact_directory("TRADEVALUE_MODEL_DIR", Path("models"))
    output = resolve_artifact_directory(
        "TRADEVALUE_EVALUATION_DIR", Path("evaluation/outputs")
    )
    paths = ArtifactPaths(
        model=directory.joinpath("skater_value_model.joblib"),
        metadata=directory.joinpath("skater_value_model_metadata.json"),
    )
    print_evaluation_diagnostics(
        evaluate_model(
            paths,
            output=output.joinpath("skater_model_test_predictions.csv"),
            context=context,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

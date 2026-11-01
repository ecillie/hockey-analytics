"""Salary-cap loading command and stdout report boundary."""

import argparse
import logging
from collections.abc import Sequence

import pandas as pd
from app.shared.cli import ExitCode
from app.config import load_environment
from app.shared.observability.domain import CommandOutcome, read_logging_settings
from app.shared.observability.errors import LoggingSettingsError
from ml.observability.services import report_ml_progress
from app.shared.observability.services import (
    configure_logging,
    start_command,
    configure_command_exceptions,
    finish_command,
)
from ml.pipelines.repository import (
    load_salary_cap,
    SALARY_CAP_QUERY as SALARY_CAP_QUERY,
)


def print_cap_diagnostics(df: pd.DataFrame) -> None:
    print("\n=== SALARY CAP DATA ===")
    print(f"Rows: {len(df):,}")

    if not df.empty:
        print(f"Seasons: {df['season'].min()} - {df['season'].max()}")

        print("\nSalary caps:")
        print(
            df[
                [
                    "season",
                    "season_label",
                    "salary_cap_dollars",
                ]
            ].to_string(index=False)
        )


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="load salary cap")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    try:
        settings = read_logging_settings(load_environment())
    except LoggingSettingsError as error:
        parser.error(str(error))
    configure_logging(settings)
    context = start_command("ml.load_salary_cap")
    configure_command_exceptions(context)
    try:
        df = load_salary_cap()
        report_ml_progress(
            context,
            event="ml.dataset_ready",
            stage="salary_cap",
            values={"rows": len(df)},
        )

        print_cap_diagnostics(df)
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

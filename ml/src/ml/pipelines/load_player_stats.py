"""Player-stat loading command and stdout report boundary."""

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
    load_player_stats,
    PLAYER_SEASON_QUERY as PLAYER_SEASON_QUERY,
)


def print_diagnostics(
    df: pd.DataFrame,
) -> None:
    print("\n=== SKATER ML DATA PIPELINE ===")
    print(f"Rows: {len(df):,}")

    if df.empty:
        print("No player-season rows found.")
        return

    print(f"Players: {df['player_id'].nunique():,}")

    print(f"Seasons: {df['season'].min()} - {df['season'].max()}")

    print(f"Columns: {len(df.columns)}")

    duplicate_count = df.duplicated(
        subset=[
            "player_id",
            "season",
        ]
    ).sum()

    print(f"Duplicate player-seasons: {duplicate_count:,}")

    advanced_available = df["ice_time_seconds"].notna().sum()

    print(f"Rows with advanced stats: {advanced_available:,} / {len(df):,}")

    print("\nRows by season:")

    print(df.groupby("season").size().sort_index().to_string())

    print("\nSample:")

    sample_columns = [
        "player_id",
        "player_name",
        "season",
        "position",
        "age",
        "games_played",
        "goals",
        "assists",
        "points",
        "individual_expected_goals",
        "on_ice_expected_goals_pct",
        "game_score",
    ]

    print(df[sample_columns].head(15).to_string(index=False))


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="load player stats")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    try:
        settings = read_logging_settings(load_environment())
    except LoggingSettingsError as error:
        parser.error(str(error))
    configure_logging(settings)
    context = start_command("ml.load_player_stats")
    configure_command_exceptions(context)
    try:
        player_stats = load_player_stats()
        report_ml_progress(
            context,
            event="ml.dataset_ready",
            stage="player_stats",
            values={"rows": len(player_stats)},
        )
        print_diagnostics(player_stats)
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

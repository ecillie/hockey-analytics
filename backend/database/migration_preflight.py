"""Reject unsafe migration attempts against an unversioned populated schema."""

import argparse
import logging
import os
from collections.abc import Sequence

from app.shared.cli import ExitCode
from app.shared.observability.domain import (
    CommandOutcome,
    InvocationContext,
    read_logging_settings,
)
from app.shared.observability.errors import LoggingSettingsError
from app.shared.observability.services import (
    configure_logging,
    start_command,
    finish_command,
)
from app.shared.environment import resolve_database_url
from app.shared.cleanup import complete_cleanup
from sqlalchemy import create_engine, text


def inspect_database(connection) -> tuple[list[str], list[str]]:
    tables = (
        connection.execute(
            text(
                """SELECT table_name FROM information_schema.tables
               WHERE table_schema = 'public'
                 AND table_type = 'BASE TABLE'
                 AND table_name <> 'alembic_version'
               ORDER BY table_name"""
            )
        )
        .scalars()
        .all()
    )
    version_table = connection.execute(
        text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
    ).scalar_one()
    versions = (
        connection.execute(text("SELECT version_num FROM alembic_version"))
        .scalars()
        .all()
        if version_table
        else []
    )
    return list(tables), list(versions)


def validate_preconditions(tables: list[str], versions: list[str]) -> str | None:
    if len(tables) > 0 and len(versions) == 0:
        return "database contains application tables but has no Alembic revision"
    if len(versions) > 1:
        return f"database reports multiple Alembic revisions: {versions}"
    return None


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
    context = start_command("migration_preflight")
    try:
        result = execute_command(context=context)
    except Exception:
        logger.exception(
            "Database check failed", extra=context.fields | {"event": "command.failed"}
        )
        finish_command(context, CommandOutcome.FAILED)
        return ExitCode.FAILURE
    finish_command(
        context,
        CommandOutcome.COMPLETED
        if result == ExitCode.SUCCESS
        else CommandOutcome.FAILED,
    )
    return result


def execute_command(*, context: InvocationContext | None = None) -> int:
    engine = create_engine(resolve_database_url(), pool_pre_ping=True)
    primary: BaseException | None = None
    try:
        with engine.connect() as connection:
            tables, versions = inspect_database(connection)
    except BaseException as failure:
        primary = failure
        raise
    finally:
        complete_cleanup((engine.dispose,), primary)

    error = validate_preconditions(tables, versions)
    if error is not None:
        logger.error(
            "%s. Verify its schema and follow the one-time baseline stamping procedure.",
            error,
            extra=({} if context is None else context.fields)
            | {
                "event": "command.verification_failed",
                "stage": "multiple_revisions"
                if len(versions) > 1
                else "unversioned_schema",
            },
        )
        return ExitCode.FAILURE
    print(
        "Migration preflight passed: "
        f"{len(tables)} application tables, revisions={versions if len(versions) > 0 else ['base']}."
    )
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())

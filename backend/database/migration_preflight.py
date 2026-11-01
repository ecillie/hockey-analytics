"""Reject unsafe migration attempts against an unversioned populated schema."""

import argparse
import logging
from collections.abc import Sequence

from app.shared.cli import ExitCode
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
    build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try:
        return execute_command()
    except Exception:
        logger.exception("Database check failed")
        return ExitCode.FAILURE


def execute_command() -> int:
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
        )
        return ExitCode.FAILURE
    print(
        "Migration preflight passed: "
        f"{len(tables)} application tables, revisions={versions if len(versions) > 0 else ['base']}."
    )
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())

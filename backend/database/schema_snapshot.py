"""Create or verify a deterministic PostgreSQL schema-catalog snapshot."""

import argparse
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.shared.cli import ExitCode
from app.shared.environment import resolve_database_url
from app.shared.cleanup import complete_cleanup
from sqlalchemy import create_engine, text


type SchemaCatalog = dict[str, list[dict[str, object]]]


def build_catalog_queries() -> dict[str, str]:
    return {
        "tables": """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
              AND table_name <> 'alembic_version'
            ORDER BY table_name
        """,
        "columns": """
            SELECT table_name, ordinal_position, column_name, data_type, udt_name,
                   is_nullable, column_default, is_identity, identity_generation
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name <> 'alembic_version'
            ORDER BY table_name, ordinal_position
        """,
        "constraints": """
            SELECT c.relname AS table_name, con.conname AS constraint_name,
                   con.contype AS constraint_type,
                   pg_get_constraintdef(con.oid, true) AS definition
            FROM pg_constraint con
            JOIN pg_class c ON c.oid = con.conrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname <> 'alembic_version'
            ORDER BY c.relname, con.conname
        """,
        "indexes": """
            SELECT tablename AS table_name, indexname AS index_name, indexdef AS definition
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename <> 'alembic_version'
            ORDER BY tablename, indexname
        """,
        "enums": """
            SELECT t.typname AS enum_name, e.enumsortorder::int AS sort_order,
                   e.enumlabel AS value
            FROM pg_type t
            JOIN pg_enum e ON e.enumtypid = t.oid
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname = 'public'
            ORDER BY t.typname, e.enumsortorder
        """,
    }


def capture_schema_catalog() -> SchemaCatalog:
    engine = create_engine(resolve_database_url(), pool_pre_ping=True)
    primary: BaseException | None = None
    try:
        with engine.connect() as connection:
            return {
                name: [dict(row) for row in connection.execute(text(query)).mappings()]
                for name, query in build_catalog_queries().items()
            }
    except BaseException as failure:
        primary = failure
        raise
    finally:
        complete_cleanup((engine.dispose,), primary)


def render_schema_catalog(value: SchemaCatalog) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str) + "\n"


snapshot = capture_schema_catalog
render = render_schema_catalog


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandOptions:
    expected: Path
    actual: Path | None
    update: bool


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expected",
        type=Path,
        default=Path(__file__).with_name("schema.snapshot.json"),
    )
    parser.add_argument("--actual", type=Path)
    parser.add_argument("--update", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    options = CommandOptions(**vars(parser.parse_args(argv)))
    logging.basicConfig(level=logging.INFO)
    try:
        return execute_command(options)
    except Exception:
        logger.exception("Command failed")
        return ExitCode.FAILURE


def execute_command(options: CommandOptions) -> int:

    actual = render_schema_catalog(capture_schema_catalog())
    if options.actual is not None:
        options.actual.parent.mkdir(parents=True, exist_ok=True)
        options.actual.write_text(actual, encoding="utf-8")
    if options.update:
        options.expected.write_text(actual, encoding="utf-8")
        print(f"Updated {options.expected}")
        return ExitCode.SUCCESS
    if not options.expected.exists():
        logger.error("schema snapshot is missing: %s", options.expected)
        return ExitCode.FAILURE
    expected = options.expected.read_text(encoding="utf-8")
    if actual != expected:
        logger.error(
            "migrated database does not match schema.snapshot.json; run schema_snapshot.py --update only after reviewing the migration."
        )
        return ExitCode.FAILURE
    print("Migrated database matches the committed schema snapshot.")
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())

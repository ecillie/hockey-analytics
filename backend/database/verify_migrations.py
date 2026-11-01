"""Validate migration history invariants without changing a database."""

import argparse
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
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
    configure_command_exceptions,
    finish_command,
)


def validate_migration_history(config_path: Path) -> list[str]:
    config = Config(str(config_path))
    scripts = ScriptDirectory.from_config(config)
    errors: list[str] = []

    heads = scripts.get_heads()
    if len(heads) != 1:
        errors.append(
            f"expected exactly one migration head, found {len(heads)}: {heads}"
        )

    revisions = list(scripts.walk_revisions(base="base", head="heads"))
    if len(revisions) == 0:
        errors.append("migration history is empty")
    for revision in revisions:
        if revision.doc is None or revision.doc == "":
            errors.append(f"migration {revision.revision} has no description")
        if revision.is_merge_point:
            errors.append(f"migration {revision.revision} is an unapproved merge point")

    return errors


validate = validate_migration_history


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandOptions:
    config: Path


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1].joinpath("alembic.ini"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    options = CommandOptions(**vars(parser.parse_args(argv)))
    try:
        settings = read_logging_settings(os.environ)
    except LoggingSettingsError as error:
        parser.error(str(error))
    configure_logging(settings)
    context = start_command("verify_migrations")
    configure_command_exceptions(context)
    try:
        result = execute_command(options, context=context)
    except Exception:
        logger.exception(
            "Command failed", extra=context.fields | {"event": "command.failed"}
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


def execute_command(
    options: CommandOptions, *, context: InvocationContext | None = None
) -> int:
    errors = validate_migration_history(options.config.resolve())
    if len(errors) > 0:
        for error in errors:
            logger.error(
                "%s",
                error,
                extra=({} if context is None else context.fields)
                | {"event": "command.verification_failed"},
            )
        return ExitCode.FAILURE
    print("Migration history has one linear head and valid revision metadata.")
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())

"""Validate migration history invariants without changing a database."""

import argparse
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from app.shared.cli import ExitCode


def validate(config_path: Path) -> list[str]:
    config = Config(str(config_path))
    scripts = ScriptDirectory.from_config(config)
    errors: list[str] = []

    heads = scripts.get_heads()
    if len(heads) != 1:
        errors.append(
            f"expected exactly one migration head, found {len(heads)}: {heads}"
        )

    revisions = list(scripts.walk_revisions(base="base", head="heads"))
    if not revisions:
        errors.append("migration history is empty")
    for revision in revisions:
        if not revision.doc:
            errors.append(f"migration {revision.revision} has no description")
        if revision.is_merge_point:
            errors.append(f"migration {revision.revision} is an unapproved merge point")

    return errors


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
    logging.basicConfig(level=logging.INFO)
    try:
        return execute_command(options)
    except Exception:
        logger.exception("Command failed")
        return ExitCode.FAILURE


def execute_command(options: CommandOptions) -> int:
    errors = validate(options.config.resolve())
    if errors:
        for error in errors:
            logger.error("%s", error)
        return ExitCode.FAILURE
    print("Migration history has one linear head and valid revision metadata.")
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())

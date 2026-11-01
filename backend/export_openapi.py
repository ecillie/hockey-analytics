"""Export or validate the committed OpenAPI contract without a live database."""

import argparse
import json
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.main import create_app
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


def _schema_text() -> str:
    return json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandOptions:
    check: bool
    output: Path


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1].joinpath("docs", "openapi.json"),
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
    context = start_command("openapi")
    configure_command_exceptions(context)
    try:
        result = export_schema(options, context=context)
    except Exception:
        logger.exception(
            "OpenAPI export failed",
            extra=context.fields | {"event": "command.failed"},
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


def export_schema(
    options: CommandOptions, *, context: InvocationContext | None = None
) -> int:
    rendered = _schema_text()

    if options.check:
        if (
            not options.output.is_file()
            or options.output.read_text(encoding="utf-8") != rendered
        ):
            logger.error(
                "%s is stale; run `uv run python backend/export_openapi.py`.",
                options.output,
                extra=({} if context is None else context.fields)
                | {"event": "command.verification_failed"},
            )
            return ExitCode.FAILURE
        return ExitCode.SUCCESS

    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {options.output}")
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())

"""Export or validate the committed OpenAPI contract without a live database."""

import argparse
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.main import create_app
from app.shared.cli import ExitCode


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
    logging.basicConfig(level=logging.INFO)
    try:
        return export_schema(options)
    except Exception:
        logger.exception("OpenAPI export failed")
        return ExitCode.FAILURE


def export_schema(options: CommandOptions) -> int:
    rendered = _schema_text()

    if options.check:
        if (
            not options.output.is_file()
            or options.output.read_text(encoding="utf-8") != rendered
        ):
            logger.error(
                "%s is stale; run `uv run python backend/export_openapi.py`.",
                options.output,
            )
            return ExitCode.FAILURE
        return ExitCode.SUCCESS

    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {options.output}")
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())

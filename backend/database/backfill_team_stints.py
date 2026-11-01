"""Repair missing season-ending team assignments from typed season statistics."""

import argparse
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from app.database import connect_database, init_db
from app.ScriptingFiles.FullDataScript.team_stints import (
    apply_team_stint_backfill,
    plan_team_stint_backfill,
)
from app.shared.cleanup import complete_cleanup
from app.shared.cli import CommandOptionError, ExitCode


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandOptions:
    apply: bool
    first_season: int | None
    last_season: int | None


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="commit the repair; default is a dry run"
    )
    parser.add_argument("--first-season", type=int)
    parser.add_argument("--last-season", type=int)
    return parser


def find_option_violation(options: CommandOptions) -> CommandOptionError | None:
    if (
        options.first_season is not None
        and options.last_season is not None
        and options.first_season > options.last_season
    ):
        return CommandOptionError(option="season range", requirement="must be ordered")
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    options = CommandOptions(**vars(parser.parse_args(argv)))
    if violation := find_option_violation(options):
        parser.error(str(violation))
    logging.basicConfig(level=logging.INFO)
    try:
        result = repair_team_stints(options)
    except Exception:
        logger.exception("Team-stint repair failed; changes were rolled back")
        return ExitCode.FAILURE
    print(json.dumps(result, sort_keys=True))
    return ExitCode.SUCCESS


def repair_team_stints(options: CommandOptions) -> dict:
    init_db()
    connection = connect_database()
    primary: BaseException | None = None
    try:
        if options.apply:
            result = apply_team_stint_backfill(
                connection,
                first_season=options.first_season,
                last_season=options.last_season,
            )
            connection.commit()
            result["applied"] = True
            return result
        result = plan_team_stint_backfill(
            connection,
            first_season=options.first_season,
            last_season=options.last_season,
        )
        connection.rollback()
        result["applied"] = False
        return result
    except BaseException as failure:
        primary = failure
        complete_cleanup((connection.rollback,), primary)
        raise
    finally:
        complete_cleanup((connection.close,), primary)


if __name__ == "__main__":
    raise SystemExit(main())

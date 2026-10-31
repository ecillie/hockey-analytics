"""Repair missing season-ending team assignments from typed season statistics."""

from __future__ import annotations

import argparse
import json
from app.database import connect_database, init_db
from app.ScriptingFiles.FullDataScript.team_stints import (
    apply_team_stint_backfill,
    plan_team_stint_backfill,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="commit the repair; default is a dry run"
    )
    parser.add_argument("--first-season", type=int)
    parser.add_argument("--last-season", type=int)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    init_db()
    connection = connect_database()
    try:
        if args.apply:
            result = apply_team_stint_backfill(
                connection,
                first_season=args.first_season,
                last_season=args.last_season,
            )
            connection.commit()
            result["applied"] = True
        else:
            result = plan_team_stint_backfill(
                connection,
                first_season=args.first_season,
                last_season=args.last_season,
            )
            connection.rollback()
            result["applied"] = False
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

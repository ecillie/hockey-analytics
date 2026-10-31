"""Run the complete schema-native ingestion pipeline."""

import argparse
import json
import logging
from collections.abc import Sequence

from app.database import init_db
from app.ScriptingFiles.FullDataScript.ingestion import run_all
from app.ScriptingFiles.FullDataScript.populate_roster_status import (
    sync_roster_status,
)
from app.ScriptingFiles.FullDataScript.roster_status.errors import (
    IncompleteRosterFeedError,
)
from app.shared.cli import ExitCode

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        summary = run_all()
        init_db()
        sync_roster_status()
    except IncompleteRosterFeedError:
        logger.exception("Ingestion refused an incomplete roster feed")
        return ExitCode.INCOMPLETE
    except Exception:
        logger.exception("Ingestion failed")
        return ExitCode.FAILURE
    print(json.dumps(summary, indent=2, sort_keys=True))
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())

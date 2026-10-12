"""Selective backfills reuse setup operations and preserve unrelated progress."""
from .run_setup import run_selected


def backfill(executor, **scope):
    return run_selected(executor, mode="backfill", **scope)


def main(argv=None):
    from app.jobs.shared.cli import setup_main
    return setup_main(argv=argv, mode="backfill")


if __name__ == "__main__":
    raise SystemExit(main())

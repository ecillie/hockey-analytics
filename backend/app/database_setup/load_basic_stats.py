"""Selected population using shared job operations; no schema or connection management."""
from .run_setup import run_selected

JOBS = ('basic_stats',)


def run(executor, **scope):
    return run_selected(executor, JOBS, **scope)


def main(argv=None):
    from app.jobs.shared.cli import setup_main
    return setup_main(argv=argv, selected=JOBS)


if __name__ == "__main__":
    raise SystemExit(main())

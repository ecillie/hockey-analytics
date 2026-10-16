"""Explicit teams_seasons entrypoint; register its operation with core_operations()."""


def run(executor, config):
    from .shared.cli import run_job
    return run_job("teams_seasons", executor, config)


def main(argv=None):
    from .shared.cli import job_main
    return job_main("teams_seasons", argv)


if __name__ == "__main__":
    raise SystemExit(main())

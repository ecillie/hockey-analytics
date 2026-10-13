"""Explicit team_rosters entrypoint; register its operation with core_operations()."""


def run(executor, config):
    from .shared.cli import run_job
    return run_job("team_rosters", executor, config)


def main(argv=None):
    from .shared.cli import job_main
    return job_main("team_rosters", argv)


if __name__ == "__main__":
    raise SystemExit(main())

"""Explicit player_profiles entrypoint; register its operation with core_operations()."""


def run(executor, config):
    from .shared.cli import run_job
    return run_job("player_profiles", executor, config)


def main(argv=None):
    from .shared.cli import job_main
    return job_main("player_profiles", argv)


if __name__ == "__main__":
    raise SystemExit(main())

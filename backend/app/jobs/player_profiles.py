"""Explicit player_profiles entrypoint; source operation is injected until its implementation phase."""


def run(executor, config):
    from .shared.cli import run_job
    return run_job("player_profiles", executor, config)


def main(argv=None):
    from .shared.cli import job_main
    return job_main("player_profiles", argv)


if __name__ == "__main__":
    raise SystemExit(main())

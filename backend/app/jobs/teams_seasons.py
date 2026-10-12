"""Explicit teams_seasons entrypoint; source operation is injected until its implementation phase."""


def run(executor, config):
    from .shared.cli import run_job
    return run_job("teams_seasons", executor, config)


def main(argv=None):
    from .shared.cli import job_main
    return job_main("teams_seasons", argv)


if __name__ == "__main__":
    raise SystemExit(main())

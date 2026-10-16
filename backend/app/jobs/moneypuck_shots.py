"""Explicit moneypuck_shots entrypoint; source operation is injected until its implementation phase."""


def run(executor, config):
    from .shared.cli import run_job
    return run_job("moneypuck_shots", executor, config)


def main(argv=None):
    from .shared.cli import job_main
    return job_main("moneypuck_shots", argv)


if __name__ == "__main__":
    raise SystemExit(main())

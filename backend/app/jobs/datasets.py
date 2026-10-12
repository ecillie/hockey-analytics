"""Explicit datasets entrypoint; source operation is injected until its implementation phase."""


def run(executor, config):
    from .shared.cli import run_job
    return run_job("datasets", executor, config)


def main(argv=None):
    from .shared.cli import job_main
    return job_main("datasets", argv)


if __name__ == "__main__":
    raise SystemExit(main())

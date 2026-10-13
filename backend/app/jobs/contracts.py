"""Explicit contracts entrypoint; register its operation with core_operations()."""


def run(executor, config):
    from .shared.cli import run_job
    return run_job("contracts", executor, config)


def main(argv=None):
    from .shared.cli import job_main
    return job_main("contracts", argv)


if __name__ == "__main__":
    raise SystemExit(main())

"""Explicit roster_reconciliation entrypoint; source operation is injected until its implementation phase."""


def run(executor, config):
    from .shared.cli import run_job
    return run_job("roster_reconciliation", executor, config)


def main(argv=None):
    from .shared.cli import job_main
    return job_main("roster_reconciliation", argv)


if __name__ == "__main__":
    raise SystemExit(main())

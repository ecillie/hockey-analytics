"""Explicit source_id_mappings entrypoint; register its operation with core_operations()."""


def run(executor, config):
    from .shared.cli import run_job
    return run_job("source_id_mappings", executor, config)


def main(argv=None):
    from .shared.cli import job_main
    return job_main("source_id_mappings", argv)


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI boundaries load an explicitly selected infrastructure runtime, never ambient DBs."""
import argparse
from importlib import import_module
import json

from .configuration import JOBS, JobConfig, execution_mode
from .execution import Executor


def parser(description):
    result = argparse.ArgumentParser(description=description)
    result.add_argument("--environment", required=True, choices=("dev", "nonprod", "prod"))
    result.add_argument("--current-season", required=True, type=int, help="Runtime-resolved source/reference season start year")
    result.add_argument("--first-season", type=int)
    result.add_argument("--last-season", type=int)
    result.add_argument("--resume", action="store_true")
    result.add_argument("--validation-only", action="store_true")
    result.add_argument("--runtime", required=True, help="Infrastructure module:factory returning an Executor for the requested environment")
    return result


def runtime(reference, environment):
    module, separator, name = reference.partition(":")
    if not separator or not module or not name:
        raise ValueError("Runtime requires module:factory")
    executor = getattr(import_module(module), name)(environment)
    if not isinstance(executor, Executor) or executor.target_environment != environment:
        raise ValueError("Runtime must supply an Executor bound to the selected environment")
    return executor


def execution_options(args, *, default_first_season):
    """Apply shared CLI defaults once for jobs, setup, and backfills."""
    return {
        "environment": args.environment,
        "target_environment": args.environment,
        "current_season": args.current_season,
        "first_season": args.first_season if args.first_season is not None else default_first_season,
        "last_season": args.last_season if args.last_season is not None else args.current_season,
        "resume": args.resume,
    }


def run_job(job, executor, config):
    """Keep named job entrypoints from accidentally running another configuration."""
    if config.job != job:
        raise ValueError("Configuration belongs to another job")
    return executor.run(config)


def report_payload(report):
    """One JSON format for ETL metrics and review issues across all entrypoints."""
    return {"run": report.run.model_dump(mode="json"), "error": report.error,
                      "issues": [issue.model_dump(mode="json") for issue in report.issues],
                      "committed_cursors": report.committed_cursors,
                      "written": report.written, "unchanged": report.unchanged}


def job_main(job, argv=None):
    command = parser(f"Run {job} with an injected replacement-pipeline runtime")
    command.add_argument("--mode", choices=("initial", "refresh", "backfill"), default="refresh")
    command.add_argument("--correction-lookback-days", type=int, default=0)
    args = command.parse_args(argv)
    try:
        config = JobConfig(job=job,
            **execution_options(args, default_first_season=args.current_season),
            mode=execution_mode((job,), args.mode, validation_only=args.validation_only),
            correction_lookback_days=args.correction_lookback_days)
        report = run_job(job, runtime(args.runtime, args.environment), config)
    except (ValueError, ImportError, AttributeError) as exc:
        command.error(str(exc))
    print(json.dumps(report_payload(report)))
    return 0 if report.complete else 1


def setup_main(argv=None, *, selected=None, mode="initial"):
    from app.database_setup.run_setup import plan_setup, run_setup
    command = parser("Populate or backfill through reusable replacement job operations")
    command.add_argument("--jobs", nargs="+", choices=selected or tuple(JOBS), default=selected or tuple(JOBS))
    args = command.parse_args(argv)
    try:
        plan = plan_setup(selected=args.jobs,
            **execution_options(args, default_first_season=2008),
            mode=execution_mode(args.jobs, mode, validation_only=args.validation_only))
        report = run_setup(runtime(args.runtime, args.environment), plan)
    except (ValueError, ImportError, AttributeError) as exc:
        command.error(str(exc))
    print(json.dumps({"complete": report.complete, "requested_jobs": len(report.requested),
                      "runs": [report_payload(result) for result in report.reports]}))
    return 0 if report.complete else 1

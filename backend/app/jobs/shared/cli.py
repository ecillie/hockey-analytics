"""CLI boundaries load an explicitly selected infrastructure runtime, never ambient DBs."""
import argparse
from importlib import import_module
import json
import logging

from app.config import _load_backend_env
from app.observability import configure_logging, log_event

from .configuration import JOBS, JobConfig, execution_mode
from .execution import Executor

logger = logging.getLogger(__name__)


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse errors and Pydantic/runtime failures can echo supplied values.
        log_event(logger, "cli.failed", level=logging.ERROR, error_code="INVALID_ARGUMENTS")
        self.exit(2)


def configure_cli():
    _load_backend_env()
    # Parse errors use stderr only. Do not create a dev file before learning the
    # explicit execution environment (which can differ from ambient ENV).
    configure_logging(environment="unknown")


def parser(description):
    result = SafeArgumentParser(description=description)
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
                      "written": report.written, "unchanged": report.unchanged,
                      "source_coverage": report.source_coverage}


def console_report(report):
    """Public CLI summary; detailed review data stays in the configured store.

    The internal report_payload contract remains available to trusted consumers.
    Never print arbitrary exception text, validation input values, or cursors.
    """
    from .data_contracts import RECORD_DEFINITIONS
    result = report_payload(report)
    result["error"] = "See structured logs and stored run/issue records." if report.error else None
    result["issues"] = [{"issue_id": str(issue.issue_id), "run_id": str(issue.run_id),
                         "dataset": issue.dataset if issue.dataset in RECORD_DEFINITIONS else "unknown",
                         "code": issue.code if issue.code in ("INVALID_RECORD", "INVALID_BATCH", "UNRESOLVED_IDENTITY", "INCOMPLETE_COLLECTION") else "VALIDATION_ISSUE",
                         "severity": issue.severity, "disposition": issue.disposition,
                         "message": "See stored validation issue."} for issue in report.issues]
    result["checkpoint_count"] = len(report.committed_cursors)
    result["committed_cursors"] = []
    coverage = []
    for item in report.source_coverage:
        entry = {key: value for key, value in item.items()
                 if key in ("season", "game_type", "game_id", "enumerated_records", "expected_records")
                 and (value is None or type(value) is int)}
        entry["dataset"] = item.get("dataset") if item.get("dataset") in RECORD_DEFINITIONS else "unknown"
        entry["status"] = item.get("status") if item.get("status") in ("available", "unavailable", "limited", "incomplete") else "unknown"
        entry["limitation"] = "See stored coverage evidence." if item.get("limitation") else None
        coverage.append(entry)
    result["source_coverage"] = coverage
    result["run"]["scope"] = {key: value for key, value in report.run.scope.items()
                              if key in ("first_season", "last_season", "correction_lookback_days") and type(value) is int}
    result["run"]["scope"]["game_types"] = list(report.run.scope.get("game_types", ()))
    return result


def job_main(job, argv=None):
    configure_cli()
    command = parser(f"Run {job} with an injected replacement-pipeline runtime")
    command.add_argument("--mode", choices=("initial", "refresh", "backfill"), default="refresh")
    command.add_argument("--correction-lookback-days", type=int, default=0)
    args = command.parse_args(argv)
    configure_logging(environment=args.environment)
    try:
        config = JobConfig(job=job,
            **execution_options(args, default_first_season=args.current_season),
            mode=execution_mode((job,), args.mode, validation_only=args.validation_only),
            correction_lookback_days=args.correction_lookback_days)
        report = run_job(job, runtime(args.runtime, args.environment), config)
    except Exception as exc:
        log_event(logger, "cli.failed", level=logging.ERROR, error=exc)
        command.error("Invalid runtime configuration")
    print(json.dumps(console_report(report)))
    return 0 if report.complete else 1


def setup_main(argv=None, *, selected=None, mode="initial"):
    configure_cli()
    from app.database_setup.run_setup import plan_setup, run_setup
    command = parser("Populate or backfill through reusable replacement job operations")
    command.add_argument("--jobs", nargs="+", choices=selected or tuple(JOBS), default=selected or tuple(JOBS))
    args = command.parse_args(argv)
    configure_logging(environment=args.environment)
    try:
        plan = plan_setup(selected=args.jobs,
            **execution_options(args, default_first_season=2008),
            mode=execution_mode(args.jobs, mode, validation_only=args.validation_only))
        report = run_setup(runtime(args.runtime, args.environment), plan)
    except Exception as exc:
        log_event(logger, "cli.failed", level=logging.ERROR, error=exc)
        command.error("Invalid runtime configuration")
    print(json.dumps({"complete": report.complete, "requested_jobs": len(report.requested),
                      "runs": [console_report(result) for result in report.reports]}))
    return 0 if report.complete else 1

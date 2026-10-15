"""Dependency-ordered data population only; infrastructure is supplied by the caller."""
from contextlib import nullcontext
from dataclasses import dataclass
import logging
from time import perf_counter
from uuid import uuid4

from app.observability import log_context, log_event, workflow_context

from app.jobs.shared.configuration import JOBS, JobConfig, execution_mode, ordered_jobs
from app.jobs.shared.access_contracts import RevisionConflict
from app.jobs.shared.execution import writer_session
from app.jobs.shared.run_tracking import RunReport, terminal_report

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SetupReport:
    reports: tuple[RunReport, ...]
    requested: tuple[JobConfig, ...]

    @property
    def complete(self):
        return len(self.reports) == len(self.requested) and all(report.complete for report in self.reports)


def plan_setup(*, selected, environment, target_environment, current_season,
               first_season=2008, last_season=None, mode="initial", resume=False):
    if mode not in ("initial", "backfill", "validation"):
        raise ValueError("Setup supports initial, backfill, or validation execution")
    selected = ordered_jobs(selected)
    execution_mode(selected, mode)
    last_season = current_season if last_season is None else last_season
    if type(first_season) is not int or type(last_season) is not int or not 2008 <= first_season <= last_season <= current_season:
        raise ValueError("Unsupported setup range")
    if last_season != current_season and any(JOBS[job].current_only for job in selected):
        raise ValueError("Current-only jobs have no work in a historical setup range")
    if any(JOBS[job].history_start > last_season for job in selected):
        raise ValueError("Selected job has no supported seasons in the request")
    seasons = range(last_season, first_season - 1, -1)
    configurations = []
    # Finish a producer's requested partitions before starting its consumers.
    # A current contract/game/dataset can depend on references from earlier seasons.
    for job in selected:
        for season in seasons:
            if season < JOBS[job].history_start or (JOBS[job].current_only and season != current_season):
                continue
            configurations.append(JobConfig(job=job, environment=environment, target_environment=target_environment,
                                  mode=mode, current_season=current_season, first_season=season,
                                  last_season=season, resume=resume))
    return tuple(configurations)


def run_setup(executor, configurations):
    configurations = tuple(configurations)
    started = perf_counter()
    with log_context(component="setup", setup_run_id=uuid4(), environment=executor.target_environment,
                     **workflow_context()):
        log_event(logger, "setup.started", requested_jobs=len(configurations))
        try:
            report = _run_setup(executor, configurations)
        except BaseException as exc:
            log_event(logger, "setup.error", level=logging.ERROR, error=exc)
            log_event(logger, "setup.finished", level=logging.ERROR, complete=False,
                      status="cancelled" if isinstance(exc, KeyboardInterrupt) else "failed",
                      duration_ms=round((perf_counter() - started) * 1000, 3))
            raise
        log_event(logger, "setup.finished", level=logging.INFO if report.complete else logging.WARNING,
                  complete=report.complete, requested_jobs=len(report.requested),
                  completed_jobs=sum(item.complete for item in report.reports),
                  duration_ms=round((perf_counter() - started) * 1000, 3))
        return report


def _run_setup(executor, configurations):
    if not configurations:
        raise ValueError("Setup requires selected work")
    environments = {config.environment for config in configurations}
    dry_modes = {config.mode == "validation" for config in configurations}
    if len(environments) != 1 or len(dry_modes) != 1 or any(config.mode not in ("initial", "backfill", "validation") for config in configurations):
        raise ValueError("Setup requires one environment and one write/validation mode")
    if any(config.target_environment != executor.target_environment for config in configurations):
        raise ValueError("Setup adapter environment differs")
    scopes = tuple(sorted({scope for config in configurations for scope in config.write_scopes}))
    read_scopes = tuple(sorted({scope for config in configurations for scope in config.read_scopes} - set(scopes)))
    dry = configurations[0].mode == "validation"
    reservation = nullcontext(None) if dry else writer_session(executor.store, configurations[0].environment, scopes, read_scopes=read_scopes)
    reports, overlay = [], {}
    snapshot = None
    if dry:
        try:
            snapshot = executor.store.snapshot(configurations[0].environment, accepted_before=executor.now())
        except Exception as exc:
            log_event(logger, "setup.error", level=logging.ERROR, error=exc)
            return SetupReport((terminal_report(configurations[0], "failed", executor.now(), str(exc)),), configurations)
    # Hold all affected scopes through setup to exclude refreshes between batches/jobs.
    try:
        with reservation as session:
            for config in configurations:
                report = executor.run(config, session=session, overlay=overlay if dry else None,
                                      validation_snapshot=snapshot)
                reports.append(report)
                if not report.complete:
                    break
    except RevisionConflict as exc:
        log_event(logger, "setup.error", level=logging.WARNING, error=exc)
        reports.append(terminal_report(configurations[0], "deferred", executor.now(), str(exc)))
    return SetupReport(tuple(reports), configurations)


def run_selected(executor, selected, **scope):
    return run_setup(executor, plan_setup(selected=selected, **scope))


def main(argv=None):
    from app.jobs.shared.cli import setup_main
    return setup_main(argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())

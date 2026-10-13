"""Run state, checkpoint cursors, and reports shared by setup and independent jobs."""
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from pydantic import JsonValue, StrictBool, StrictInt, field_validator, model_validator

from .coverage import POLICY_VERSION
from .data_contracts import CONTRACT_VERSION, PipelineRun, Record, RunCounters, ValidationIssue, canonical_json


@dataclass(frozen=True)
class RunReport:
    run: PipelineRun
    issues: tuple[ValidationIssue, ...] = ()
    committed_cursors: tuple[object, ...] = ()
    written: int = 0
    unchanged: int = 0
    error: str | None = None
    source_coverage: tuple[dict, ...] = ()

    @property
    def complete(self):
        return self.run.status in ("succeeded", "no_change")


class CheckpointCursor(Record):
    version: StrictInt = 1
    position: JsonValue
    complete: StrictBool

    @field_validator("version")
    @classmethod
    def supported_version(cls, value):
        if value != 1:
            raise ValueError("Unsupported checkpoint cursor version")
        return value

    @model_validator(mode="after")
    def known_position(self):
        if self.position is None:
            raise ValueError("Checkpoint requires an explicit position")
        return self

    @property
    def fingerprint(self):
        return canonical_json(self.position)


def start_run(config, now: datetime):
    return PipelineRun(run_id=uuid4(), job=config.job, environment=config.environment,
                       mode=config.mode, scope=config.scope, status="running", started_at=now,
                       counters=RunCounters(), contract_version=CONTRACT_VERSION,
                       coverage_policy_version=POLICY_VERSION)


def update_run(run, **changes):
    # Validate changes; Pydantic model_copy(update=...) would bypass these contracts.
    return PipelineRun(**{**run.model_dump(), **changes})


def finish_run(run, status, counters, now):
    return update_run(run, status=status, counters=counters, finished_at=now)


def terminal_report(config, status, now, error=None):
    run = start_run(config, now)
    return RunReport(finish_run(run, status, run.counters, now), error=error)


@dataclass
class RunTracker:
    run: PipelineRun
    issues: list[ValidationIssue] = field(default_factory=list)
    committed_cursors: list[object] = field(default_factory=list)
    written: int = 0
    unchanged: int = 0
    completed_batches: int = 0
    domain_changes: int = 0
    persisted: bool = False

    def count(self, **increments):
        self.run = self.updated_run(**increments)

    def updated_run(self, **increments):
        """Preview validated counts without mutating progress before a commit."""
        counts = self.run.counters.model_dump()
        return update_run(self.run, counters=RunCounters(**{
            **counts, **{name: counts[name] + value for name, value in increments.items()}}))

    @property
    def failure_status(self):
        return "partial" if self.completed_batches else "failed"

    def report(self, status, now, error=None):
        terminal = finish_run(self.run, status, self.run.counters, now)
        return RunReport(terminal, tuple(self.issues), tuple(self.committed_cursors),
                         self.written, self.unchanged, error)

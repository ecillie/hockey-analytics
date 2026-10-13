"""Extract, normalize/validate, and atomically load against injected operations."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from time import sleep
from typing import Any, Callable, Iterable, Mapping

from .access_contracts import DataReader, DataStore, RevisionConflict, Snapshot, make_checkpoint_write
from .configuration import JOBS, JobConfig
from .data_contracts import Checkpoint, Environment, PipelineRun, Record, RECORD_DEFINITIONS
from .identity import resolve_identity
from .run_tracking import CheckpointCursor, RunReport, RunTracker, start_run, terminal_report, update_run
from .source_requests import SourceClient
from .upload import prepare_writes, upload_batch
from .validation import CollectionBatch, ValidatedBatch, validate_collection


def utc_now():
    return datetime.now(timezone.utc)


def normalized_payload(item, context):
    return item.payload


@dataclass(frozen=True)
class JobOperation:
    collect: Callable[[ExecutionContext, object], Iterable[CollectionBatch]]
    normalize: Callable = normalized_payload
    # Adapters verify the requested prerequisite scope/coverage/freshness.
    ready: Callable[[ExecutionContext], bool] | None = None


@dataclass
class ExecutionContext:
    config: JobConfig
    run: PipelineRun
    reader: DataReader
    snapshot: Snapshot
    overlay: dict[tuple[str, tuple[Any, ...]], Record] = field(default_factory=dict)
    client: SourceClient | None = None
    source_coverage: list[dict] = field(default_factory=list)

    def lookup(self, dataset, key):
        if (dataset, key) in self.overlay:
            return self.overlay[dataset, key]
        stored = self.reader.get(dataset, key, snapshot=self.snapshot)
        return stored.write.decoded() if stored else None

    def resolve(self, source, entity_type, source_id):
        return resolve_identity(source, entity_type, source_id, self.lookup)

    def find_unique(self, dataset, fields, values):
        for (name, key), record in self.overlay.items():
            if name == dataset and tuple(getattr(record, field) for field in fields) == values:
                return record
        stored = self.reader.find_unique(dataset, fields, values, snapshot=self.snapshot)
        if stored is None:
            return None
        record = self.lookup(dataset, stored.write.key)
        return record if tuple(getattr(record, field) for field in fields) == values else None


@dataclass
class WriterSession:
    store: DataStore
    environment: Environment
    scopes: tuple[str, ...]
    read_scopes: tuple[str, ...] = ()
    active: bool = True


@contextmanager
def writer_session(store, environment, scopes, *, read_scopes=()):
    with store.writer_lease(environment, conflict_scopes=scopes, read_scopes=read_scopes):
        session = WriterSession(store, environment, scopes, read_scopes)
        try:
            yield session
        finally:
            session.active = False


class Executor:
    def __init__(self, store: DataStore, operations: Mapping[str, JobOperation], *,
                 target_environment: Environment, client: SourceClient | None = None,
                 now: Callable[[], datetime] = utc_now, pause: Callable[[float], None] = sleep):
        self.store, self.operations = store, dict(operations)
        self.target_environment, self.client, self.now, self.pause = target_environment, client, now, pause

    def run(self, config: JobConfig, *, session: WriterSession | None = None,
            overlay=None, validation_snapshot: Snapshot | None = None) -> RunReport:
        if config.target_environment != self.target_environment or config.environment != self.target_environment:
            raise ValueError("Adapter environment does not match execution")
        if validation_snapshot is not None and (config.mode != "validation" or validation_snapshot.environment != config.environment):
            raise ValueError("Validation snapshot does not match execution")
        if config.mode == "validation":
            return self._run(config, overlay=overlay, snapshot=validation_snapshot)
        if session is not None:
            if (not session.active or session.store is not self.store or session.environment != config.environment
                    or not set(config.write_scopes) <= set(session.scopes)
                    or not set(config.read_scopes) <= set(session.scopes) | set(session.read_scopes)):
                raise ValueError("Writer session does not cover execution")
            return self._run(config)
        try:
            with writer_session(self.store, config.environment, config.write_scopes, read_scopes=config.read_scopes):
                return self._run(config)
        except RevisionConflict as exc:
            return terminal_report(config, "deferred", self.now(), str(exc))

    def _run(self, config, *, overlay=None, snapshot=None):
        state = RunTracker(start_run(config, self.now()))
        context = None
        try:
            context = ExecutionContext(config, state.run, self.store,
                snapshot or self.store.snapshot(config.environment, accepted_before=self.now()),
                overlay if overlay is not None else {}, self.client)
            if not config.enabled:
                return self._finish(context, state, "disabled")
            self._persist_run(context, state)
            operation = self.operations.get(config.job)
            if operation is None:
                return self._finish(context, state, "deferred", "Source operation is not implemented/registered")
            if (JOBS[config.job].inputs and operation.ready is None) or (operation.ready is not None and operation.ready(context) is not True):
                return self._finish(context, state, "deferred", "Required inputs are not verified ready")
            progress = self.store.checkpoint(config.environment, config.job, config.scope_key, snapshot=context.snapshot) if config.resume else None
            saved = CheckpointCursor.model_validate(progress[0].cursor) if progress else None
            if saved and saved.complete:
                return self._finish(context, state, "no_change")
            cursor = saved.position if saved else None
            seen = {saved.fingerprint} if saved else set()
            final = False
            for index, batch in enumerate(operation.collect(context, cursor)):
                if index >= config.max_batches:
                    raise ValueError("Collection exceeds batch limit")
                if not isinstance(batch, CollectionBatch):
                    raise ValueError("Collector must yield CollectionBatch records")
                batch.validate_limits(config.max_batch_records)
                position = CheckpointCursor(position=batch.cursor, complete=batch.final)
                if position.fingerprint in seen:
                    raise ValueError("Collection cursor repeated; progress must advance")
                seen.add(position.fingerprint)
                state.count(read=len(batch.records))
                context.run = state.run
                checked = validate_collection(batch, context, operation.normalize)
                state.issues.extend(checked.issues)
                if checked.issues:
                    state.count(unresolved=checked.unresolved, rejected=len(batch.records) - checked.unresolved)
                    self._persist_run(context, state, extra=prepare_writes(context, checked.review_records))
                    return self._finish(context, state, state.failure_status,
                                        "Batch held for review; checkpoint not advanced")
                self._accept_batch(context, state, batch, checked, position)
                final = batch.final
                if final:
                    break
            if not final:
                raise ValueError("Source enumeration ended without an explicit final batch")
            return self._finish(context, state, "succeeded" if config.mode == "validation" or state.domain_changes else "no_change")
        except (Exception, KeyboardInterrupt) as exc:
            status = "cancelled" if isinstance(exc, KeyboardInterrupt) else state.failure_status
            if context is None or not state.persisted:
                return state.report(status, self.now(), str(exc))
            return self._finish(context, state, status, str(exc))

    def _persist_run(self, context, state, *, run=None, extra=()):
        if context.config.mode == "validation":
            return
        context.snapshot = self.store.snapshot(context.config.environment, accepted_before=self.now())
        writes = prepare_writes(context, (("pipeline_runs", run or state.run),))
        upload_batch(self.store, state.run, context.config.conflict_scopes, (*writes, *extra), pause=self.pause)
        state.persisted = True
        context.snapshot = self.store.snapshot(context.config.environment, accepted_before=self.now())

    def _finish(self, context, state, status, error=None):
        report = replace(state.report(status, self.now(), error), source_coverage=tuple(context.source_coverage))
        if context.source_coverage:
            report = replace(report, run=update_run(report.run,
                scope={**report.run.scope, "source_coverage": context.source_coverage}))
        try:
            self._persist_run(context, state, run=report.run)
        except Exception as exc:
            return replace(state.report(state.failure_status, self.now(),
                                f"{error + '; ' if error else ''}{exc}; terminal run persistence failed"),
                           source_coverage=tuple(context.source_coverage))
        return report

    def _accept_batch(self, context, state, batch, checked: ValidatedBatch, position):
        records = checked.observation_records + checked.records
        links = {(dataset, RECORD_DEFINITIONS[dataset].key(record)): (item.observation.observation_id,)
                 for item, (dataset, record) in zip(batch.records, checked.records)}
        writes = prepare_writes(context, records, links)
        running = state.updated_run(accepted=len(batch.records))
        if context.config.mode == "validation":
            for dataset, record in records:
                context.overlay[dataset, RECORD_DEFINITIONS[dataset].key(record)] = record
        else:
            config = context.config
            previous = self.store.checkpoint(config.environment, config.job, config.scope_key, snapshot=context.snapshot)
            checkpoint = Checkpoint(environment=config.environment, job=config.job, scope_key=config.scope_key,
                cursor=position.model_dump(), committed_run_id=state.run.run_id, committed_at=self.now())
            progress_writes = prepare_writes(context, (("pipeline_runs", running),))
            receipt = upload_batch(self.store, running, config.conflict_scopes, (*writes, *progress_writes),
                checkpoint=make_checkpoint_write(checkpoint, expected_revision=previous[1] if previous else None), pause=self.pause)
            state.domain_changes += sum(write.dataset in JOBS[config.job].outputs for write in writes)
            state.written += receipt.written - len(progress_writes)
            state.unchanged += len(records) - len(writes) + receipt.unchanged
            state.committed_cursors.append(position.position)
        state.run = running
        context.run = running
        state.completed_batches += 1
        if context.config.mode != "validation":
            context.snapshot = self.store.snapshot(config.environment, accepted_before=self.now())

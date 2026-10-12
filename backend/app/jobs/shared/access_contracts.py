"""Injectable persistence contracts. Concrete adapters belong to database infrastructure.

An adapter must atomically commit a batch, its provenance, issues, receipt, and
checkpoint. These definitions describe that boundary; they do not connect to or
write a database. Contract tests use an in-memory adapter in the test package.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from hashlib import sha256
import json
from typing import Annotated, Any, Protocol
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, TypeAdapter, model_validator

from .data_contracts import (
    Checkpoint, Count, Digest, Environment, Id, Record, RECORD_DEFINITIONS,
    Text, canonical_json, validate_record,
)


class Snapshot(Record):
    environment: Environment
    token: Text
    accepted_before: AwareDatetime


class RecordWrite(Record):
    dataset: Text
    payload: bytes
    content_digest: Digest
    expected_revision: Id | None
    observation_ids: tuple[UUID, ...]

    def decoded(self) -> Record:
        if sha256(self.payload).hexdigest() != self.content_digest:
            raise ValueError("Record payload digest differs")
        record = validate_record(self.dataset, self.payload)
        if canonical_json(record.model_dump(mode="json")) != self.payload:
            raise ValueError("Record payload is not canonical JSON")
        return record

    @property
    def key(self) -> tuple[Any, ...]:
        return RECORD_DEFINITIONS[self.dataset].key(self.decoded())


def make_write(dataset: str, record: Record, *, expected_revision: int | None,
               observation_ids: tuple[UUID, ...] = ()) -> RecordWrite:
    """None means create-only; an integer requires that exact current revision."""
    if type(record) is not RECORD_DEFINITIONS[dataset].model:
        raise ValueError("Record model does not match its dataset")
    checked = validate_record(dataset, record.model_dump())
    payload = canonical_json(checked.model_dump(mode="json"))
    return RecordWrite(dataset=dataset, payload=payload,
                       content_digest=sha256(payload).hexdigest(),
                       expected_revision=expected_revision, observation_ids=observation_ids)


class StoredRecord(Record):
    write: RecordWrite
    revision: Id
    accepted_at: AwareDatetime
    run_id: UUID


class CheckpointWrite(Record):
    write: RecordWrite

    @model_validator(mode="after")
    def checkpoint_only(self) -> CheckpointWrite:
        if self.write.dataset != "checkpoints":
            raise ValueError("Checkpoint boundary requires a checkpoint record")
        self.write.decoded()
        return self

    @property
    def checkpoint(self) -> Checkpoint:
        return self.write.decoded()

    @property
    def expected_revision(self) -> int | None:
        return self.write.expected_revision


def make_checkpoint_write(checkpoint: Checkpoint, *, expected_revision: int | None) -> CheckpointWrite:
    return CheckpointWrite(write=make_write("checkpoints", checkpoint, expected_revision=expected_revision))


class AcceptedBatch(Record):
    batch_id: UUID
    run_id: UUID
    environment: Environment
    conflict_scopes: Annotated[tuple[Text, ...], Field(min_length=1)]
    writes: tuple[RecordWrite, ...]
    checkpoint: CheckpointWrite | None = None

    def validate_envelope(self) -> None:
        if len(self.conflict_scopes) != len(set(self.conflict_scopes)):
            raise ValueError("Conflict scopes must be distinct")
        identities = []
        for write in self.writes:
            identities.append((write.dataset, write.key))
            if len(write.observation_ids) != len(set(write.observation_ids)):
                raise ValueError("Duplicate provenance links")
            if RECORD_DEFINITIONS[write.dataset].append_only and write.expected_revision is not None:
                raise ValueError("Append-only identities cannot be revised")
            if write.dataset not in {"pipeline_runs", "checkpoints", "validation_issues", "source_observations", "datasets", "model_versions", "predictions", "roster_overrides"} and not write.observation_ids:
                raise ValueError("Accepted source records require provenance")
            if write.dataset == "checkpoints":
                raise ValueError("Use the batch's checkpoint write boundary")
            if write.dataset == "pipeline_runs" and write.decoded().environment != self.environment:
                raise ValueError("Run environment differs from batch")
        if len(identities) != len(set(identities)):
            raise ValueError("A batch contains duplicate record keys")
        if self.checkpoint is not None:
            checkpoint = self.checkpoint.checkpoint
            if checkpoint.environment != self.environment or checkpoint.committed_run_id != self.run_id:
                raise ValueError("Checkpoint environment/run differs from batch")

    @property
    def content_digest(self) -> str:
        self.validate_envelope()
        return sha256(canonical_json(self.model_dump(mode="json"))).hexdigest()


class CommitReceipt(Record):
    batch_id: UUID
    environment: Environment
    content_digest: Digest
    committed_at: AwareDatetime
    written: Count
    unchanged: Count
    checkpoint_revision: Id | None


class ReadRequest(Record):
    dataset: Text
    snapshot: Snapshot
    scope_json: bytes = b"{}"
    limit: Annotated[Id, Field(le=10000)] = 1000
    cursor: Text | None = None
    include_history: StrictBool = False

    def validate_scope(self) -> None:
        if self.dataset not in RECORD_DEFINITIONS:
            raise ValueError("Unknown read dataset")
        scope = json.loads(self.scope_json)
        if not isinstance(scope, dict) or canonical_json(scope) != self.scope_json:
            raise ValueError("Read scope requires a canonical JSON object")
        if not set(scope).issubset(RECORD_DEFINITIONS[self.dataset].model.model_fields):
            raise ValueError("Unknown read filter field")
        for field, value in scope.items():
            annotation = RECORD_DEFINITIONS[self.dataset].model.model_fields[field].rebuild_annotation()
            TypeAdapter(annotation).validate_json(canonical_json(value), strict=True)
            if isinstance(value, str) and not value.strip():
                raise ValueError("Blank read filter value")
            if field == "game_type" and type(value) is not int:
                raise ValueError("Game type filter must be an integer")


class ReadPage(Record):
    snapshot: Snapshot
    records: tuple[StoredRecord, ...]
    next_cursor: Text | None


class RevisionConflict(RuntimeError):
    """The current revision changed, or a create-only identity already exists."""


class IdempotencyConflict(RuntimeError):
    """A batch ID was reused with different content."""


class DataReader(Protocol):
    def snapshot(self, environment: Environment, *, accepted_before: datetime) -> Snapshot: ...

    def get(self, dataset: str, key: tuple[Any, ...], *, snapshot: Snapshot,
            revision: int | None = None) -> StoredRecord | None: ...

    def scan(self, request: ReadRequest) -> ReadPage: ...

    def find_unique(self, dataset: str, fields: tuple[str, ...], values: tuple[Any, ...],
                    *, snapshot: Snapshot) -> StoredRecord | None: ...

    def checkpoint(self, environment: Environment, job: str, scope_key: str,
                   *, snapshot: Snapshot) -> tuple[Checkpoint, int] | None: ...


class BatchTransaction(Protocol):
    def stage(self, batch: AcceptedBatch) -> None: ...

    def commit(self) -> CommitReceipt: ...


class DataStore(DataReader, Protocol):
    def transaction(self, environment: Environment, *, conflict_scopes: tuple[str, ...]
                    ) -> AbstractContextManager[BatchTransaction]: ...

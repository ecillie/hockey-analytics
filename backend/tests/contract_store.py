"""Contract-test double only. It is not a database adapter or job executor."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from uuid import uuid4

from app.jobs.shared.access_contracts import (
    CommitReceipt, IdempotencyConflict, ReadPage, RevisionConflict, Snapshot,
    StoredRecord, make_write,
)
from app.jobs.shared.data_contracts import RECORD_DEFINITIONS, validate_batch


class ContractStore:
    def __init__(self, fixtures=()):
        self.rows, self.checkpoints, self.receipts, self.snapshots = {}, {}, {}, {}
        self.locked = set()
        self.leased = set()
        self.read_leased = {}
        self.fail_before_commit = False
        self.now = datetime(2026, 10, 10, 12, 2, tzinfo=timezone.utc)
        for dataset, value in fixtures:
            if dataset == "checkpoints":
                continue  # Fixture bootstrap has no committed processing progress.
            write = make_write(dataset, value, expected_revision=None)
            self.rows["dev", dataset, write.key] = [StoredRecord(
                write=write, revision=1, accepted_at=self.now, run_id=uuid4())]

    def snapshot(self, environment, *, accepted_before):
        snapshot = Snapshot(environment=environment, token=str(uuid4()), accepted_before=accepted_before)
        view = {key: tuple(row for row in values if row.accepted_at <= snapshot.accepted_before)
                for key, values in self.rows.items() if key[0] == environment}
        checkpoints = {key[2]: (values[-1].write.decoded(), values[-1].revision)
                       for key, values in view.items() if key[1] == "checkpoints" and values}
        self.snapshots[snapshot.token] = view, checkpoints, snapshot
        return snapshot

    def _view(self, snapshot):
        rows, checkpoints, expected = self.snapshots[snapshot.token]
        if snapshot != expected:
            raise ValueError("Snapshot cannot be reused for another environment or cutoff")
        return rows, checkpoints

    def get(self, dataset, key, *, snapshot, revision=None):
        values = self._view(snapshot)[0].get((snapshot.environment, dataset, key), ())
        return next((row for row in reversed(values) if revision is None or row.revision == revision), None)

    def find_unique(self, dataset, fields, values, *, snapshot):
        definition = RECORD_DEFINITIONS[dataset]
        if fields not in (definition.key_fields, *definition.unique_keys):
            raise ValueError("Lookup requires a declared identity key")
        found = []
        for (environment, name, key), revisions in self._view(snapshot)[0].items():
            if name == dataset and revisions:
                record = revisions[-1].write.decoded()
                if tuple(getattr(record, field) for field in fields) == values:
                    found.append(revisions[-1])
        if len(found) > 1:
            raise ValueError("Ambiguous source identity")
        return found[0] if found else None

    def scan(self, request):
        request.validate_scope()
        filters = json.loads(request.scope_json)
        selected = []
        for (_, dataset, key), revisions in self._view(request.snapshot)[0].items():
            if dataset == request.dataset:
                for row in revisions if request.include_history else revisions[-1:]:
                    value = row.write.decoded().model_dump(mode="json")
                    if all(value[field] == expected for field, expected in filters.items()):
                        selected.append(row)
        selected.sort(key=lambda row: (repr(row.write.key), row.revision))
        # Opaque cursor is bound to this exact query/snapshot, not a bare offset.
        fingerprint = (request.dataset, request.snapshot.token, request.scope_json, request.include_history)
        offset = 0
        if request.cursor is not None:
            stored_fingerprint, offset = self.cursors[request.cursor]
            if fingerprint != stored_fingerprint:
                raise ValueError("Cursor differs from its query/snapshot")
        if not hasattr(self, "cursors"):
            self.cursors = {}
        cursor = None
        if offset + request.limit < len(selected):
            cursor = str(uuid4())
            self.cursors[cursor] = fingerprint, offset + request.limit
        return ReadPage(snapshot=request.snapshot, records=tuple(selected[offset:offset + request.limit]), next_cursor=cursor)

    def checkpoint(self, environment, job, scope_key, *, snapshot):
        if environment != snapshot.environment:
            raise ValueError("Checkpoint environment differs from snapshot")
        return self._view(snapshot)[1].get((environment, job, scope_key))

    @contextmanager
    def writer_lease(self, environment, *, conflict_scopes, read_scopes=()):
        locks = {(environment, scope) for scope in conflict_scopes}
        reads = {(environment, scope) for scope in read_scopes} - locks
        if not locks or locks & (self.leased | self.read_leased.keys()) or reads & self.leased:
            raise RevisionConflict("Conflicting writer lease")
        self.leased.update(locks)
        for key in reads:
            self.read_leased[key] = self.read_leased.get(key, 0) + 1
        try:
            yield
        finally:
            self.leased.difference_update(locks)
            for key in reads:
                if self.read_leased[key] == 1:
                    del self.read_leased[key]
                else:
                    self.read_leased[key] -= 1

    @contextmanager
    def transaction(self, environment, *, conflict_scopes):
        locks = {(environment, scope) for scope in conflict_scopes}
        if not locks or locks & self.locked:
            raise RevisionConflict("Conflicting writer")
        self.locked.update(locks)
        try:
            yield ContractTransaction(self, environment, conflict_scopes)
        finally:
            self.locked.difference_update(locks)


class ContractTransaction:
    def __init__(self, store, environment, scopes):
        self.store, self.environment, self.scopes = store, environment, scopes
        self.batch = None

    def stage(self, batch):
        if self.batch is not None:
            raise ValueError("One batch per transaction")
        batch.validate_envelope()
        if batch.environment != self.environment or set(batch.conflict_scopes) != set(self.scopes):
            raise ValueError("Batch differs from its transaction scope")
        self.batch = batch

    def commit(self):
        batch, store = self.batch, self.store
        if batch is None:
            raise ValueError("No staged batch")
        receipt_key = self.environment, batch.batch_id
        if receipt_key in store.receipts:
            receipt = store.receipts[receipt_key]
            if receipt.content_digest != batch.content_digest:
                raise IdempotencyConflict("Batch content differs")
            return receipt
        staged = dict(store.rows)
        records = tuple((write.dataset, write.decoded()) for write in batch.writes)

        def lookup(dataset, key):
            values = staged.get((self.environment, dataset, key), ())
            return values[-1].write.decoded() if values else None

        validate_batch(records, lookup)
        written = unchanged = 0
        for write in batch.writes:
            key = self.environment, write.dataset, write.key
            previous = staged.get(key, ())
            revision = previous[-1].revision if previous else None
            if revision != write.expected_revision:
                raise RevisionConflict("Record revision differs")
            for observation_id in write.observation_ids:
                local = any(name == "source_observations" and value.observation_id == observation_id for name, value in records)
                if not local and lookup("source_observations", (observation_id,)) is None:
                    raise ValueError("Missing provenance observation")
            for fields in RECORD_DEFINITIONS[write.dataset].unique_keys:
                value = write.decoded()
                values = tuple(getattr(value, field) for field in fields)
                if None not in values:
                    for (environment, dataset, identity), other in staged.items():
                        if environment == self.environment and dataset == write.dataset and identity != write.key:
                            if tuple(getattr(other[-1].write.decoded(), field) for field in fields) == values:
                                raise ValueError("Duplicate accepted source identity")
            if previous and previous[-1].write.content_digest == write.content_digest and previous[-1].write.observation_ids == write.observation_ids:
                unchanged += 1
                continue
            staged[key] = [*previous, StoredRecord(write=write, revision=(revision or 0) + 1,
                accepted_at=store.now, run_id=batch.run_id)]
            written += 1
        if lookup("pipeline_runs", (batch.run_id,)) is None:
            raise ValueError("Batch run must exist")
        # Manifests pin exact accepted inputs and digests, including prior revisions.
        for dataset, value in records:
            if dataset == "datasets":
                for item in value.input_revisions:
                    from app.jobs.shared.access_contracts import canonical_json
                    history = next((versions for (environment, name, key), versions in staged.items()
                                    if environment == self.environment and name == item.dataset
                                    and canonical_json(RECORD_DEFINITIONS[name].json_key(versions[-1].write.decoded())) == canonical_json(item.record_key)), ())
                    pinned = next((row for row in history if row.revision == item.revision), None)
                    if pinned is None or pinned.write.content_digest != item.content_digest or pinned.accepted_at > value.cutoff:
                        raise ValueError("Manifest input revision/digest/cutoff differs")
        checkpoints = dict(store.checkpoints)
        checkpoint_revision = None
        if batch.checkpoint is not None:
            checkpoint = batch.checkpoint.checkpoint
            key = checkpoint.environment, checkpoint.job, checkpoint.scope_key
            old = checkpoints.get(key)
            revision = old[1] if old else None
            if revision != batch.checkpoint.expected_revision:
                raise RevisionConflict("Checkpoint revision differs")
            checkpoint_revision = (revision or 0) + 1
            checkpoints[key] = checkpoint, checkpoint_revision
            identity = self.environment, "checkpoints", key
            staged[identity] = [*staged.get(identity, ()), StoredRecord(
                write=batch.checkpoint.write, revision=checkpoint_revision,
                accepted_at=store.now, run_id=batch.run_id)]
        if store.fail_before_commit:
            raise RuntimeError("Injected interruption")
        receipt = CommitReceipt(batch_id=batch.batch_id, environment=self.environment,
            content_digest=batch.content_digest, committed_at=store.now, written=written,
            unchanged=unchanged, checkpoint_revision=checkpoint_revision)
        store.rows, store.checkpoints = staged, checkpoints
        store.receipts[receipt_key] = receipt
        return receipt

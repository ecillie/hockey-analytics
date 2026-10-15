"""PostgreSQL implementation of the sealed pipeline access contracts.

One database has one explicitly initialized environment. Session advisory locks
are the lease: disconnect/crash releases them, and a lost session cannot reconnect
inside a reservation. All commits take a short global transaction lock, keeping
CAS, cross-record validation, receipt recovery and snapshot watermarks atomic.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from hashlib import sha256
import base64
import hmac
import json
import secrets
from uuid import uuid4

from pydantic_core import to_jsonable_python
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.jobs.shared.access_contracts import (
    AcceptedBatch, CommitReceipt, IdempotencyConflict, ReadPage, RecordWrite, RevisionConflict,
    Snapshot, StoredRecord,
)
from app.jobs.shared.data_contracts import RECORD_DEFINITIONS, canonical_json, validate_batch
from app.jobs.shared.upload import UploadInterrupted

METADATA = frozenset(("pipeline_runs", "source_observations", "validation_issues", "checkpoints"))


def lock_key(scope):
    return int.from_bytes(sha256(("tradevalue-pipeline/" + scope).encode()).digest()[:8], "big", signed=True)


def initialize_target(engine, environment):
    """Explicit one-time binding after migrations; never retarget a database."""
    if environment not in ("dev", "nonprod", "prod"):
        raise ValueError("Unsupported target environment")
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key("target")})
        connection.execute(text("""INSERT INTO pipeline_target
            (environment, target_id, token_secret) VALUES (:env, :id, :secret)
            ON CONFLICT (singleton) DO NOTHING"""),
            {"env": environment, "id": str(uuid4()), "secret": secrets.token_hex(32)})
        actual = connection.execute(text("SELECT environment FROM pipeline_target")).scalar_one()
        if actual != environment:
            raise ValueError("Database target environment differs")


class PostgresStore:
    def __init__(self, engine, environment):
        if engine.dialect.name != "postgresql":
            raise ValueError("The pipeline store requires PostgreSQL")
        self.engine, self.environment = engine, environment
        self._lease = ContextVar(f"pipeline_lease_{id(self)}", default=None)
        with engine.connect() as connection:
            target = self._target(connection)
            self.target_id, self.secret = str(target.target_id), target.token_secret.encode()

    def _target(self, connection):
        target = connection.execute(text("SELECT * FROM public.pipeline_target")).one_or_none()
        if target is None or target.environment != self.environment:
            raise ValueError("Database target is uninitialized or environment differs")
        if hasattr(self, "target_id") and str(target.target_id) != self.target_id:
            raise ValueError("Database target identity changed")
        return target

    def _environment(self, environment):
        if environment != self.environment:
            raise ValueError("Database target environment differs")

    def _seal(self, payload):
        body = base64.urlsafe_b64encode(canonical_json(payload)).decode()
        return body + "." + hmac.new(self.secret, body.encode(), "sha256").hexdigest()

    def _unseal(self, token):
        try:
            body, signature = token.split(".")
            if not hmac.compare_digest(signature, hmac.new(self.secret, body.encode(), "sha256").hexdigest()):
                raise ValueError()
            return json.loads(base64.urlsafe_b64decode(body))
        except (ValueError, TypeError, UnicodeError) as exc:
            raise ValueError("Invalid snapshot/cursor token") from exc

    def snapshot(self, environment, *, accepted_before):
        self._environment(environment)
        # Pydantic also rejects naive datetimes and normalizes UTC.
        checked = Snapshot(environment=environment, token="pending", accepted_before=accepted_before)
        with self.engine.connect() as connection:
            self._target(connection)
            position = connection.execute(text("SELECT COALESCE(MAX(sequence),0) FROM public.pipeline_records")).scalar_one()
        token = self._seal({"target": self.target_id, "environment": environment,
                            "cutoff": checked.accepted_before.isoformat(), "position": position})
        return Snapshot(environment=environment, token=token, accepted_before=checked.accepted_before)

    def _view(self, snapshot):
        self._environment(snapshot.environment)
        payload = self._unseal(snapshot.token)
        if (payload.get("target"), payload.get("environment"), payload.get("cutoff")) != (
                self.target_id, snapshot.environment, snapshot.accepted_before.isoformat()):
            raise ValueError("Snapshot differs from its environment/cutoff/target")
        return payload["position"]

    @staticmethod
    def _stored(row):
        return StoredRecord(write=RecordWrite.model_validate_json(canonical_json(row.envelope)),
                            revision=row.revision, accepted_at=row.accepted_at, run_id=row.run_id)

    def get(self, dataset, key, *, snapshot, revision=None):
        if dataset not in RECORD_DEFINITIONS:
            raise ValueError("Unknown read dataset")
        position = self._view(snapshot)
        with self.engine.connect() as connection:
            self._target(connection)
            row = connection.execute(text("""SELECT * FROM public.pipeline_records
                WHERE dataset=:dataset AND record_key=:key AND sequence<=:position
                AND accepted_at<=:cutoff AND (:revision IS NULL OR revision=:revision)
                ORDER BY revision DESC LIMIT 1"""),
                {"dataset": dataset, "key": canonical_json(to_jsonable_python(key)).decode(), "position": position,
                 "cutoff": snapshot.accepted_before, "revision": revision}).one_or_none()
        return self._stored(row) if row else None

    def scan(self, request):
        request.validate_scope()
        position = self._view(request.snapshot)
        fingerprint = sha256(canonical_json([request.dataset, request.snapshot.token,
            request.scope_json.decode(), request.include_history])).hexdigest()
        after = None
        if request.cursor:
            cursor = self._unseal(request.cursor)
            if cursor.get("query") != fingerprint:
                raise ValueError("Cursor differs from its query/snapshot")
            after = cursor["after"]
        # Filter after selecting the visible revision, never resurrect a prior
        # matching revision when a correction changes a filtered field.
        selection = "*" if request.include_history else "DISTINCT ON (record_key) *"
        ordering = "record_key, revision DESC" if not request.include_history else "record_key, revision"
        query = f"""WITH visible AS (SELECT {selection} FROM public.pipeline_records
            WHERE dataset=:dataset AND sequence<=:position AND accepted_at<=:cutoff
            ORDER BY {ordering}) SELECT * FROM visible WHERE payload @> CAST(:filters AS jsonb)
            AND (:after_key IS NULL OR (record_key, revision) > (:after_key, :after_revision))
            ORDER BY record_key, revision LIMIT :limit"""
        with self.engine.connect() as connection:
            self._target(connection)
            rows = connection.execute(text(query), {"dataset": request.dataset, "position": position,
                "cutoff": request.snapshot.accepted_before, "filters": request.scope_json.decode(),
                "after_key": after[0] if after else None, "after_revision": after[1] if after else 0,
                "limit": request.limit + 1}).all()
        selected = rows[:request.limit]
        cursor = self._seal({"query": fingerprint, "after": [selected[-1].record_key, selected[-1].revision]}) if len(rows) > request.limit else None
        return ReadPage(snapshot=request.snapshot, records=tuple(self._stored(row) for row in selected), next_cursor=cursor)

    def find_unique(self, dataset, fields, values, *, snapshot):
        from app.jobs.shared.access_contracts import ReadRequest
        definition = RECORD_DEFINITIONS[dataset]
        if fields not in (definition.key_fields, *definition.unique_keys) or len(fields) != len(values):
            raise ValueError("Lookup requires a declared identity key")
        page = self.scan(ReadRequest(dataset=dataset, snapshot=snapshot,
            scope_json=canonical_json(dict(zip(fields, values))), limit=2))
        if len(page.records) > 1:
            raise ValueError("Ambiguous source identity")
        return page.records[0] if page.records else None

    def checkpoint(self, environment, job, scope_key, *, snapshot):
        self._environment(environment)
        row = self.get("checkpoints", (environment, job, scope_key), snapshot=snapshot)
        return (row.write.decoded(), row.revision) if row else None

    @contextmanager
    def writer_lease(self, environment, *, conflict_scopes, read_scopes=()):
        self._environment(environment)
        if self._lease.get() is not None or not conflict_scopes:
            raise RevisionConflict("Nested/empty writer reservation")
        writes, reads = set(conflict_scopes), set(read_scopes) - set(conflict_scopes)
        if any(not scope.startswith("dataset:") or scope[8:] not in RECORD_DEFINITIONS for scope in writes | reads):
            raise ValueError("Writer reservations require declared dataset scopes")
        connection = self.engine.connect()
        token = None
        try:
            self._target(connection)
            for scope in sorted(writes | reads):
                function = "pg_try_advisory_lock" if scope in writes else "pg_try_advisory_lock_shared"
                if not connection.execute(text(f"SELECT {function}(:key)"), {"key": lock_key(scope)}).scalar_one():
                    raise RevisionConflict("Conflicting writer reservation")
            connection.commit()
            token = self._lease.set((connection, writes, reads))
            yield
        finally:
            if token is not None:
                self._lease.reset(token)
            try:
                if not connection.invalidated and not connection.closed:
                    connection.rollback()
                    connection.execute(text("SELECT pg_advisory_unlock_all()"))
                    connection.commit()
            finally:
                connection.close()

    @contextmanager
    def transaction(self, environment, *, conflict_scopes):
        self._environment(environment)
        transaction = PostgresTransaction(self, tuple(conflict_scopes))
        try:
            yield transaction
        finally:
            transaction.active = False


class PostgresTransaction:
    def __init__(self, store, scopes):
        self.store, self.scopes, self.batch, self.active = store, scopes, None, True

    def stage(self, batch):
        if not self.active or self.batch is not None:
            raise ValueError("One batch per active transaction")
        batch = AcceptedBatch.model_validate_json(batch.model_dump_json())
        batch.validate_envelope()
        if batch.environment != self.store.environment or set(batch.conflict_scopes) != set(self.scopes):
            raise ValueError("Batch differs from its transaction scope")
        domain = {"dataset:" + write.dataset for write in batch.writes if write.dataset not in METADATA}
        if not self.scopes or not domain <= set(self.scopes):
            raise ValueError("Batch writes require their actual dataset scopes")
        self.batch = batch

    def commit(self):
        if not self.active or self.batch is None:
            raise ValueError("No staged batch in an active transaction")
        store = self.store
        lease = store._lease.get()
        try:
            if lease is None:
                with store.writer_lease(store.environment, conflict_scopes=self.scopes):
                    return self.commit()
            connection, writes, reads = lease
            if connection.invalidated or connection.closed:
                raise RevisionConflict("Writer reservation session was lost; start a fresh run")
            domain = {"dataset:" + write.dataset for write in self.batch.writes if write.dataset not in METADATA}
            if not domain <= writes or not set(self.scopes) <= writes | reads:
                raise ValueError("Transaction is outside the writer reservation")
            with connection.begin():
                store._target(connection)
                connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key("commit")})
                return self._commit(connection)
        except DBAPIError as exc:
            # Do not expose connection strings or SQL parameters in reports.
            if lease is not None and exc.connection_invalidated:
                raise RevisionConflict("Writer reservation session was lost; start a fresh run") from exc
            raise UploadInterrupted("Database commit interrupted; retry exact batch") from exc

    def _commit(self, connection):
        batch, store = self.batch, self.store
        old_receipt = connection.execute(text("SELECT receipt FROM public.pipeline_receipts WHERE batch_id=:id"), {"id": str(batch.batch_id)}).scalar_one_or_none()
        if old_receipt is not None:
            receipt = CommitReceipt.model_validate_json(canonical_json(old_receipt))
            if receipt.content_digest != batch.content_digest:
                raise IdempotencyConflict("Batch content differs")
            return receipt

        def current(dataset, key):
            return connection.execute(text("""SELECT * FROM public.pipeline_records
                WHERE dataset=:dataset AND record_key=:key ORDER BY revision DESC LIMIT 1"""),
                {"dataset": dataset, "key": canonical_json(to_jsonable_python(key)).decode()}).one_or_none()

        def lookup(dataset, key):
            row = current(dataset, key)
            return store._stored(row).write.decoded() if row else None

        records = tuple((write.dataset, write.decoded()) for write in batch.writes)
        validate_batch(records, lookup)
        local = {(name, RECORD_DEFINITIONS[name].key(value)): value for name, value in records}
        resolve = lambda dataset, key: local.get((dataset, key)) or lookup(dataset, key)
        if resolve("pipeline_runs", (batch.run_id,)) is None:
            raise ValueError("Batch run must exist")
        now = connection.execute(text("SELECT clock_timestamp()" )).scalar_one()
        written = unchanged = 0
        checkpoint_revision = None
        all_writes = (*batch.writes, *((batch.checkpoint.write,) if batch.checkpoint else ()))
        for write in all_writes:
            value = write.decoded()
            previous = current(write.dataset, write.key)
            revision = previous.revision if previous else None
            if revision != write.expected_revision:
                raise RevisionConflict("Checkpoint revision differs" if write.dataset == "checkpoints" else "Record revision differs")
            for observation_id in write.observation_ids:
                if resolve("source_observations", (observation_id,)) is None:
                    raise ValueError("Missing provenance observation")
            for fields in RECORD_DEFINITIONS[write.dataset].unique_keys:
                values = tuple(getattr(value, field) for field in fields)
                if None not in values:
                    duplicate = connection.execute(text("""SELECT 1 FROM public.pipeline_current
                        WHERE dataset=:dataset AND record_key<>:key AND payload @> CAST(:fields AS jsonb) LIMIT 1"""),
                        {"dataset": write.dataset, "key": canonical_json(to_jsonable_python(write.key)).decode(),
                         "fields": canonical_json(dict(zip(fields, values))).decode()}).first()
                    if duplicate:
                        raise ValueError("Duplicate accepted source identity")
            if write.dataset == "datasets":
                if value.quality_results.get("passed") is not True or value.point_in_time_supported:
                    raise ValueError("Dataset publication requires passed quality and supported temporal policy")
                for item in value.input_revisions:
                    pinned = connection.execute(text("""SELECT * FROM public.pipeline_records
                        WHERE dataset=:dataset AND record_key=:key AND revision=:revision"""),
                        {"dataset": item.dataset, "key": canonical_json(item.record_key).decode(), "revision": item.revision}).one_or_none()
                    if (pinned is None or store._stored(pinned).write.content_digest != item.content_digest
                            or pinned.accepted_at > value.cutoff):
                        raise ValueError("Manifest input revision/digest/cutoff differs")
            if previous and previous.envelope["content_digest"] == write.content_digest and previous.envelope["observation_ids"] == [str(item) for item in write.observation_ids]:
                unchanged += 1
                continue
            next_revision = (revision or 0) + 1
            connection.execute(text("""INSERT INTO public.pipeline_records
                (dataset,record_key,revision,accepted_at,run_id,envelope,payload)
                VALUES (:dataset,:key,:revision,:at,:run,CAST(:envelope AS jsonb),CAST(:payload AS jsonb))"""),
                {"dataset": write.dataset, "key": canonical_json(to_jsonable_python(write.key)).decode(), "revision": next_revision,
                 "at": now, "run": str(batch.run_id), "envelope": write.model_dump_json(), "payload": write.payload.decode()})
            if write.dataset == "checkpoints":
                checkpoint_revision = next_revision
            else:
                written += 1
        receipt = CommitReceipt(batch_id=batch.batch_id, environment=store.environment,
            content_digest=batch.content_digest, committed_at=now, written=written,
            unchanged=unchanged, checkpoint_revision=checkpoint_revision)
        connection.execute(text("INSERT INTO public.pipeline_receipts VALUES (:id,CAST(:receipt AS jsonb))"),
            {"id": str(batch.batch_id), "receipt": receipt.model_dump_json()})
        return receipt

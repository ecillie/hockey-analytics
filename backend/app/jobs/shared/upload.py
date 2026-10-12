"""Write preparation and atomic uploads shared by data, issues, and run tracking."""
from time import sleep
from uuid import uuid4

from .access_contracts import AcceptedBatch, IdempotencyConflict, RevisionConflict, make_write
from .data_contracts import RECORD_DEFINITIONS
from .retries import backoff_delay


class UploadInterrupted(RuntimeError):
    """Adapter may raise this for a retryable or uncertain commit outcome."""


def prepare_writes(context, records, observation_links=None):
    """Compare against one accepted view and seal changes into immutable envelopes."""
    writes = []
    for dataset, record in records:
        key = RECORD_DEFINITIONS[dataset].key(record)
        previous = context.reader.get(dataset, key, snapshot=context.snapshot)
        old = context.overlay.get((dataset, key))
        if old is None and previous is not None:
            old = previous.write.decoded()
        if old == record:
            continue
        if old is not None and RECORD_DEFINITIONS[dataset].append_only:
            raise ValueError("Append-only identity cannot be corrected")
        writes.append(make_write(dataset, record, expected_revision=previous.revision if previous else None,
                      observation_ids=(observation_links or {}).get((dataset, key), ())))
    return tuple(writes)


def upload_batch(store, run, scopes, writes, *, checkpoint=None, pause=sleep):
    batch = AcceptedBatch(batch_id=uuid4(), run_id=run.run_id, environment=run.environment,
                          conflict_scopes=scopes, writes=writes, checkpoint=checkpoint)
    return upload(store, batch, pause=pause)


def upload(store, batch, *, attempts=3, pause=sleep):
    if type(attempts) is not int or not 1 <= attempts <= 10:
        raise ValueError("Upload attempts must be between 1 and 10")
    batch.validate_envelope()
    for attempt in range(attempts):
        try:
            with store.transaction(batch.environment, conflict_scopes=batch.conflict_scopes) as transaction:
                transaction.stage(batch)
                return transaction.commit()
        except (RevisionConflict, IdempotencyConflict):
            raise
        except UploadInterrupted:
            if attempt + 1 == attempts:
                raise
            pause(backoff_delay(attempt, 8))

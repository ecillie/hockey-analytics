from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID, uuid4

import pytest

from app.jobs.shared.access_contracts import (
    AcceptedBatch, IdempotencyConflict, ReadRequest, RevisionConflict,
    canonical_json, make_checkpoint_write, make_write,
)
from .contract_store import ContractStore
from .test_data_contracts import record, records


OBSERVATION = UUID("00000000-0000-0000-0000-000000000001")
RUN = UUID("00000000-0000-0000-0000-000000000002")
SCOPES = ("player_profiles:7",)
CUTOFF = datetime(2027, 1, 1, tzinfo=timezone.utc)


def batch(*writes, checkpoint=None, **overrides):
    return AcceptedBatch(batch_id=uuid4(), run_id=RUN, environment="dev",
                         conflict_scopes=SCOPES, writes=writes, checkpoint=checkpoint, **overrides)


def profile(**changes):
    return make_write("player_profiles", record("player_profiles", **changes),
                      expected_revision=1, observation_ids=(OBSERVATION,))


def commit(store, value):
    with store.transaction(value.environment, conflict_scopes=value.conflict_scopes) as transaction:
        transaction.stage(value)
        return transaction.commit()


def test_atomic_revision_history_checkpoint_and_identical_retry():
    store = ContractStore(records())
    before = store.snapshot("dev", accepted_before=CUTOFF)
    checkpoint = make_checkpoint_write(record("checkpoints"), expected_revision=None)
    value = batch(profile(last_name="Corrected"), checkpoint=checkpoint)
    receipt = commit(store, value)
    assert (receipt.written, receipt.checkpoint_revision) == (1, 1)
    assert commit(store, value) == receipt
    after = store.snapshot("dev", accepted_before=CUTOFF)
    assert store.get("player_profiles", (7,), snapshot=before).write.decoded().last_name == "Skater"
    latest = store.get("player_profiles", (7,), snapshot=after)
    assert latest.revision == 2 and latest.write.decoded().last_name == "Corrected"
    assert store.get("player_profiles", (7,), snapshot=after, revision=1).write.decoded().last_name == "Skater"
    assert store.checkpoint("dev", "rosters", "team:10", snapshot=after)[1] == 1
    progress = store.get("checkpoints", ("dev", "rosters", "team:10"), snapshot=after)
    assert progress.revision == 1
    early = store.snapshot("dev", accepted_before=datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert store.checkpoint("dev", "rosters", "team:10", snapshot=early) is None


def test_interruption_and_uncommitted_exit_leave_no_partial_state():
    store = ContractStore(records())
    rows, checkpoints, receipts = dict(store.rows), dict(store.checkpoints), dict(store.receipts)
    value = batch(profile(last_name="Correction"), checkpoint=make_checkpoint_write(record("checkpoints"), expected_revision=None))
    with store.transaction("dev", conflict_scopes=SCOPES) as transaction:
        transaction.stage(value)
    assert store.rows == rows
    store.fail_before_commit = True
    with pytest.raises(RuntimeError, match="Injected"):
        commit(store, value)
    assert (store.rows, store.checkpoints, store.receipts) == (rows, checkpoints, receipts)
    assert not store.locked
    store.fail_before_commit = False
    assert commit(store, value).written == 1


def test_stale_record_or_checkpoint_conflict_rolls_back_all_writes():
    store = ContractStore(records())
    checkpoint = make_checkpoint_write(record("checkpoints"), expected_revision=None)
    commit(store, batch(profile(last_name="First"), checkpoint=checkpoint))
    rows = dict(store.rows)
    with pytest.raises(RevisionConflict, match="Record revision"):
        commit(store, batch(profile(last_name="Stale")))
    fresh_write = make_write("player_profiles", record("player_profiles", last_name="Second"), expected_revision=2, observation_ids=(OBSERVATION,))
    with pytest.raises(RevisionConflict, match="Checkpoint revision"):
        commit(store, batch(fresh_write, checkpoint=checkpoint))
    assert store.rows == rows


def test_content_changed_under_a_committed_batch_id_is_a_conflict():
    store = ContractStore(records())
    original = batch(profile())
    commit(store, original)
    changed = original.model_copy(update={"writes": (profile(last_name="Different"),)})
    with pytest.raises(IdempotencyConflict):
        commit(store, changed)


def test_identical_payload_and_provenance_are_no_change_with_matching_revision():
    store = ContractStore(records())
    value = batch(profile())
    commit(store, value)  # Adds provenance to the seeded fixture revision.
    write = make_write("player_profiles", record("player_profiles"), expected_revision=2, observation_ids=(OBSERVATION,))
    assert commit(store, batch(write)).unchanged == 1


def test_snapshots_and_conflicting_writers_are_environment_scoped():
    store = ContractStore(records())
    prod = store.snapshot("prod", accepted_before=CUTOFF)
    assert store.get("player_profiles", (7,), snapshot=prod) is None
    with pytest.raises(ValueError, match="another environment"):
        store.get("player_profiles", (7,), snapshot=prod.model_copy(update={"environment": "dev"}))
    with store.transaction("dev", conflict_scopes=SCOPES):
        with pytest.raises(RevisionConflict, match="Conflicting writer"):
            with store.transaction("dev", conflict_scopes=SCOPES):
                pass
        with store.transaction("prod", conflict_scopes=SCOPES):
            pass


def test_missing_provenance_or_duplicate_source_identity_blocks_the_batch():
    store = ContractStore(records())
    missing = make_write("player_profiles", record("player_profiles"), expected_revision=1, observation_ids=(uuid4(),))
    with pytest.raises(ValueError, match="Missing provenance"):
        commit(store, batch(missing))
    duplicate = make_write("player_profiles", record("player_profiles", player_id=9), expected_revision=None, observation_ids=(OBSERVATION,))
    with pytest.raises(ValueError, match="Duplicate accepted source identity"):
        commit(store, batch(duplicate))


def test_manifest_pins_real_input_revision_digest_and_cutoff():
    store = ContractStore(records())
    stored = store.get("basic_stats", ("Cap Space", 7, 2025, 2, "TOTAL", None, "skater"), snapshot=store.snapshot("dev", accepted_before=CUTOFF))
    item = dict(dataset="basic_stats", record_key=list(stored.write.key), revision=1, content_digest=stored.write.content_digest)
    manifest = record("datasets", version="v2", cutoff="2026-10-10T12:03:00Z", input_revisions=[item])
    write = make_write("datasets", manifest, expected_revision=None)
    assert commit(store, batch(write)).written == 1
    bad = record("datasets", version="v3", cutoff="2026-10-10T12:03:00Z", input_revisions=[dict(item, content_digest="0" * 64)])
    with pytest.raises(ValueError, match="Manifest input"):
        commit(store, batch(make_write("datasets", bad, expected_revision=None)))


def test_paginated_reads_are_bound_to_a_consistent_snapshot_and_scope():
    store = ContractStore(records())
    snapshot = store.snapshot("dev", accepted_before=CUTOFF)
    request = ReadRequest(dataset="player_profiles", snapshot=snapshot, limit=1)
    page = store.scan(request)
    assert page.next_cursor is not None
    second = store.scan(request.model_copy(update={"cursor": page.next_cursor}))
    assert len(second.records) == 1 and second.next_cursor is None
    assert page.records[0].write.key != second.records[0].write.key
    later = store.snapshot("dev", accepted_before=CUTOFF)
    with pytest.raises(ValueError, match="Cursor differs"):
        store.scan(request.model_copy(update={"snapshot": later, "cursor": page.next_cursor}))
    filtered = store.scan(ReadRequest(dataset="player_profiles", snapshot=snapshot, scope_json=canonical_json({"player_id": 7})))
    assert [row.write.key for row in filtered.records] == [(7,)]
    early = store.snapshot("dev", accepted_before=datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert store.get("player_profiles", (7,), snapshot=early) is None
    assert store.find_unique("player_profiles", ("nhl_player_id",), (1007,), snapshot=snapshot).write.key == (7,)


def test_immutable_payload_detects_corruption_and_model_construct_bypass():
    write = profile()
    with pytest.raises(ValueError, match="digest differs"):
        write.model_copy(update={"payload": b"{}"}).decoded()
    bad_json = b'{ "player_id":7 }'
    with pytest.raises(ValueError):
        write.model_copy(update={"payload": bad_json, "content_digest": sha256(bad_json).hexdigest()}).decoded()
    with pytest.raises(ValueError, match="model does not match"):
        make_write("teams", record("player_profiles"), expected_revision=None)


def test_checkpoint_serialization_seals_mutable_cursors():
    checkpoint = record("checkpoints")
    write = make_checkpoint_write(checkpoint, expected_revision=None)
    checkpoint.cursor["page"] = 99
    assert write.checkpoint.cursor == {"page": 1}
    copy = write.checkpoint
    copy.cursor["page"] = 55
    assert write.checkpoint.cursor == {"page": 1}


@pytest.mark.parametrize("change", [
    {"writes": (make_write("teams", record("teams"), expected_revision=None),)},
    {"writes": (profile(), profile())},
    {"conflict_scopes": ("same", "same")},
    {"writes": (make_write("source_observations", record("source_observations"), expected_revision=1),)},
    {"writes": (make_write("checkpoints", record("checkpoints"), expected_revision=None),)},
    {"checkpoint": make_checkpoint_write(record("checkpoints", environment="prod"), expected_revision=None)},
])
def test_invalid_batch_envelopes_do_not_reach_storage(change):
    value = batch(profile()).model_copy(update=change)
    with pytest.raises(ValueError):
        value.validate_envelope()


@pytest.mark.parametrize("scope", [b"[]", b'{ "player_id":7 }', b'{"not_a_field":7}', b'{"team_id":"10"}'])
def test_invalid_read_scopes_are_rejected(scope):
    store = ContractStore(records())
    request = ReadRequest(dataset="teams", snapshot=store.snapshot("dev", accepted_before=CUTOFF), scope_json=scope)
    with pytest.raises(ValueError):
        request.validate_scope()

"""Real PostgreSQL conformance, failure injection and consumer compatibility."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from database.pipeline.store import PostgresStore, initialize_target
from app.jobs.shared.access_contracts import (
    AcceptedBatch, IdempotencyConflict, ReadRequest, RevisionConflict,
    make_checkpoint_write, make_write,
)
from app.jobs.shared.data_contracts import RECORD_DEFINITIONS, canonical_json
from app.jobs.shared.execution import Executor
from app.api.service import TradeValueService
from .execution_fixtures import fixture_operations, config
from .test_data_contracts import record, records

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL requires a disposable migrated PostgreSQL database")
RUN = record("pipeline_runs").run_id
OBS = record("source_observations").observation_id
SCOPES = ("dataset:player_profiles",)


@pytest.fixture
def engine():
    engine = create_engine(URL, pool_size=8, max_overflow=8, hide_parameters=True)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE pipeline_records, pipeline_receipts RESTART IDENTITY"))
    initialize_target(engine, "dev")
    yield engine
    engine.dispose()


@pytest.fixture
def store(engine):
    return PostgresStore(engine, "dev")


def commit(store, batch):
    with store.transaction(batch.environment, conflict_scopes=batch.conflict_scopes) as transaction:
        transaction.stage(batch)
        return transaction.commit()


def seed(store):
    items = [(dataset, value) for dataset, value in records() if dataset not in ("datasets", "checkpoints")]
    scopes = tuple("dataset:" + name for name in RECORD_DEFINITIONS)
    batch = AcceptedBatch(batch_id=uuid4(), run_id=RUN, environment="dev", conflict_scopes=scopes,
        writes=tuple(make_write(dataset, value, expected_revision=None,
            observation_ids=() if dataset in ("pipeline_runs", "source_observations", "validation_issues", "model_versions", "predictions", "roster_overrides") else (OBS,)) for dataset, value in items))
    return commit(store, batch)


def snapshot(store):
    return store.snapshot("dev", accepted_before=datetime.now(timezone.utc) + timedelta(seconds=1))


def correction(store, name="Corrected", revision=1, checkpoint=None):
    write = make_write("player_profiles", record("player_profiles", last_name=name),
        expected_revision=revision, observation_ids=(OBS,))
    return AcceptedBatch(batch_id=uuid4(), run_id=RUN, environment="dev", conflict_scopes=SCOPES,
        writes=(write,), checkpoint=checkpoint)


def test_durable_history_snapshot_cutoff_cas_checkpoint_and_retry(store, engine):
    seed(store)
    before = snapshot(store)
    batch = correction(store, checkpoint=make_checkpoint_write(record("checkpoints"), expected_revision=None))
    receipt = commit(store, batch)
    assert (receipt.written, receipt.checkpoint_revision) == (1, 1)
    other = PostgresStore(engine, "dev")
    assert commit(other, batch) == receipt  # durable receipt, independent adapter
    assert other.get("player_profiles", (7,), snapshot=before).revision == 1
    after = snapshot(other)
    assert other.get("player_profiles", (7,), snapshot=after).write.decoded().last_name == "Corrected"
    assert other.get("player_profiles", (7,), revision=1, snapshot=after).revision == 1
    assert other.checkpoint("dev", "rosters", "team:10", snapshot=after)[1] == 1
    with pytest.raises(RevisionConflict, match="Record revision"):
        commit(store, correction(store))
    with pytest.raises(IdempotencyConflict):
        commit(store, batch.model_copy(update={"writes": correction(store, "Changed", 2).writes}))
    early = store.snapshot("dev", accepted_before=datetime(2000, 1, 1, tzinfo=timezone.utc))
    assert store.get("player_profiles", (7,), snapshot=early) is None


def test_checkpoint_failure_rolls_back_records_and_receipt(store, engine):
    seed(store)
    checkpoint = make_checkpoint_write(record("checkpoints"), expected_revision=None)
    commit(store, correction(store, checkpoint=checkpoint))
    bad = correction(store, "Must roll back", 2, checkpoint)
    with pytest.raises(RevisionConflict, match="Checkpoint revision"):
        commit(store, bad)
    assert store.get("player_profiles", (7,), snapshot=snapshot(store)).revision == 2
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1 FROM pipeline_receipts WHERE batch_id=:id"), {"id": str(bad.batch_id)}).first() is None


def test_uncommitted_and_exceptional_exit_do_not_publish(store):
    seed(store)
    batch = correction(store)
    with store.transaction("dev", conflict_scopes=SCOPES) as tx:
        tx.stage(batch)
    with pytest.raises(RuntimeError):
        with store.transaction("dev", conflict_scopes=SCOPES) as tx:
            tx.stage(batch)
            raise RuntimeError("interrupted before commit")
    assert store.get("player_profiles", (7,), snapshot=snapshot(store)).revision == 1


def test_snapshot_pagination_filters_are_bound_and_do_not_resurrect_history(store):
    seed(store)
    request = ReadRequest(dataset="player_profiles", snapshot=snapshot(store), limit=1)
    first = store.scan(request)
    assert first.next_cursor
    commit(store, correction(store))
    second = store.scan(request.model_copy(update={"cursor": first.next_cursor}))
    assert second.next_cursor is None
    assert first.records[0].write.key != second.records[0].write.key
    for changed in ({"snapshot": snapshot(store)}, {"scope_json": canonical_json({"player_id": 7})}):
        with pytest.raises(ValueError, match="Cursor differs"):
            store.scan(request.model_copy(update={"cursor": first.next_cursor, **changed}))
    filtered = ReadRequest(dataset="player_profiles", snapshot=snapshot(store), scope_json=canonical_json({"player_id": 7, "last_name": "Skater"}))
    assert store.scan(filtered).records == ()
    assert store.find_unique("player_profiles", ("nhl_player_id",), (1007,), snapshot=snapshot(store)).write.key == (7,)
    with pytest.raises(ValueError):
        store.get("player_profiles", (7,), snapshot=request.snapshot.model_copy(update={"environment": "prod"}))
    with pytest.raises(ValueError):
        store.get("player_profiles", (7,), snapshot=request.snapshot.model_copy(update={"accepted_before": datetime(2000,1,1,tzinfo=timezone.utc)}))


def test_unique_identity_provenance_scope_and_target_are_enforced(store, engine):
    seed(store)
    with pytest.raises(ValueError, match="environment"):
        PostgresStore(engine, "prod")
    with pytest.raises(ValueError, match="environment"):
        initialize_target(engine, "prod")
    duplicate = make_write("player_profiles", record("player_profiles", player_id=99), expected_revision=None, observation_ids=(OBS,))
    with pytest.raises(ValueError, match="Duplicate accepted"):
        commit(store, correction(store).model_copy(update={"writes": (duplicate,)}))
    missing = make_write("player_profiles", record("player_profiles", last_name="Missing"), expected_revision=1, observation_ids=(uuid4(),))
    with pytest.raises(ValueError, match="Missing provenance"):
        commit(store, correction(store).model_copy(update={"writes": (missing,)}))
    with pytest.raises(ValueError, match="actual dataset"):
        commit(store, correction(store).model_copy(update={"conflict_scopes": ("dataset:teams",)}))


def test_independent_database_sessions_honor_shared_and_refill_reservations(store, engine):
    other = PostgresStore(engine, "dev")
    with store.writer_lease("dev", conflict_scopes=("dataset:teams",), read_scopes=("dataset:player_profiles",)):
        with pytest.raises(RevisionConflict):
            with other.writer_lease("dev", conflict_scopes=SCOPES):
                pass
        with other.writer_lease("dev", conflict_scopes=("dataset:games",), read_scopes=SCOPES):
            pass
    # Whole refill reserves every selected producer, so a refresh cannot slip
    # between jobs or batches even if it uses a new process/connection.
    with store.writer_lease("dev", conflict_scopes=("dataset:teams", "dataset:player_profiles")):
        report = Executor(other, fixture_operations(), target_environment="dev").run(config("player_profiles"))
        assert report.run.status == "deferred"


def test_session_loss_releases_lease_and_fences_the_old_writer(store, engine):
    seed(store)
    other = PostgresStore(engine, "dev")
    with store.writer_lease("dev", conflict_scopes=SCOPES):
        connection = store._lease.get()[0]
        pid = connection.execute(text("SELECT pg_backend_pid()" )).scalar_one()
        connection.commit()
        with engine.begin() as killer:
            assert killer.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}).scalar_one()
        with pytest.raises(RevisionConflict, match="session was lost"):
            commit(store, correction(store))
        with other.writer_lease("dev", conflict_scopes=SCOPES):
            pass
    assert store.get("player_profiles", (7,), snapshot=snapshot(store)).revision == 1


def test_uncertain_commit_response_recovers_the_exact_durable_receipt(store, engine):
    seed(store)
    batch = correction(store)
    # Commit has reached the server; simulate the response being lost by
    # discarding the adapter and retrying the sealed envelope on a new session.
    receipt = commit(store, batch)
    recovered = commit(PostgresStore(engine, "dev"), batch)
    assert recovered == receipt
    assert store.get("player_profiles", (7,), snapshot=snapshot(store)).revision == 2


def test_simultaneous_stale_writers_have_one_winner(store, engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    seed(store)
    barrier = Barrier(2)
    def writer(name):
        adapter = PostgresStore(engine, "dev")
        value = correction(adapter, name)
        barrier.wait(timeout=5)
        try:
            commit(adapter, value)
            return "committed"
        except RevisionConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(writer, ("First", "Second")))
    assert sorted(results) == ["committed", "conflict"]
    assert store.get("player_profiles", (7,), snapshot=snapshot(store)).revision == 2


def test_disconnect_before_receipt_insert_rolls_back_whole_batch(store, engine):
    from sqlalchemy import event
    seed(store)
    value = correction(store)
    killer_engine = create_engine(URL)
    def disconnect(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO public.pipeline_receipts"):
            pid = connection.connection.driver_connection.get_backend_pid()
            with killer_engine.begin() as killer:
                killer.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid":pid})
    event.listen(engine, "before_cursor_execute", disconnect)
    try:
        with pytest.raises(RevisionConflict, match="session was lost"):
            commit(store, value)
    finally:
        event.remove(engine, "before_cursor_execute", disconnect)
        killer_engine.dispose()
    assert store.get("player_profiles", (7,), snapshot=snapshot(store)).revision == 1
    assert commit(PostgresStore(engine, "dev"), value).written == 1


def test_real_setup_refresh_interruption_and_resume(store):
    from .execution_fixtures import source, batch, TEAM, SEASON
    from app.jobs.shared.execution import JobOperation
    from app.database_setup.run_setup import plan_setup, run_setup
    # Collecting the second page fails after the first page was committed.
    def interrupted(ctx, cursor):
        yield batch(source("teams", TEAM), cursor=1, final=False)
        raise OSError("upstream interrupted")
    executor = Executor(store, {"teams_seasons": JobOperation(interrupted)}, target_environment="dev")
    result = executor.run(config())
    assert result.run.status == "partial" and result.committed_cursors == (1,)
    def resume(ctx, cursor):
        assert cursor == 1
        yield batch(source("seasons", SEASON), cursor=2)
    executor.operations["teams_seasons"] = JobOperation(resume)
    assert executor.run(config(resume=True)).complete
    executor.operations = fixture_operations()
    plan = plan_setup(selected=("teams_seasons", "player_profiles", "team_rosters"), environment="dev",
        target_environment="dev", current_season=2026, first_season=2026)
    assert run_setup(executor, plan).complete
    assert executor.run(config(mode="refresh")).complete


def test_api_and_ml_read_replacement_rows_with_legacy_units_and_total_preference(store, engine):
    seed(store)
    with Session(engine) as session:
        session.execute(text("SET LOCAL search_path=pipeline_api,public"))
        service = TradeValueService(session)
        identity = service.player_identity(7)
        assert identity["id"] == 7 and identity["rosterStatus"] == "ACTIVE"
        stats = service.player_stats(7, 2025)
        assert stats["traditional"]["gamesPlayed"] == 82
        assert stats["traditional"]["goals"] == 30
        assert service.contract(7, 2025)["seasons"][0]["capHitCents"] == 800000000
        assert service.players(2025, None, None, None, None, "name", "asc", 1, 1)["pagination"]["pageSize"] == 1
        from ml.pipelines.load_player_stats import PLAYER_SEASON_QUERY
        from ml.pipelines.load_salary_cap import SALARY_CAP_QUERY
        rows = session.execute(PLAYER_SEASON_QUERY).mappings().all()
        skater = next(row for row in rows if row["player_id"] == 7)
        assert skater["games_played"] == 82
        assert skater["power_play_points"] is None
        assert session.execute(SALARY_CAP_QUERY).mappings().first()["salary_cap_cents"] == 9550000000


def test_dataset_publication_pins_real_revisions_and_keeps_prior_artifacts(store, tmp_path):
    from app.jobs.dataset_processing import dataset_operation, reproduce_dataset
    from database.pipeline.artifacts import LocalArtifacts
    from .test_dataset_processing import fixture_inputs, DEFINITION
    seed(store)
    # A separate population with complete eligible source/target seasons.
    inputs = fixture_inputs()
    snap = snapshot(store)
    writes = []
    for dataset, rows in inputs.items():
        for row in rows:
            previous = store.get(dataset, row.write.key, snapshot=snap)
            writes.append(make_write(dataset, row.write.decoded(), expected_revision=previous.revision if previous else None, observation_ids=(OBS,)))
    scopes = tuple("dataset:"+name for name in inputs)
    commit(store, AcceptedBatch(batch_id=uuid4(), run_id=RUN, environment="dev", conflict_scopes=scopes, writes=tuple(writes)))
    cutoff = datetime.now(timezone.utc)
    artifacts = LocalArtifacts(tmp_path)
    executor = Executor(store, {"datasets": dataset_operation((DEFINITION,), artifacts, cutoff=cutoff)}, target_environment="dev")
    scope = config("datasets", first_season=2020, last_season=2023)
    report = executor.run(scope)
    assert report.complete, report.error
    manifests = store.scan(ReadRequest(dataset="datasets", snapshot=snapshot(store))).records
    assert len(manifests) == 1
    manifest = manifests[0].write.decoded()
    assert sha256(artifacts.read(manifest.content_digest)).hexdigest() == manifest.content_digest
    assert manifest.row_count == 8
    assert executor.run(scope).run.status == "no_change"
    # Exact revisions needed by a published dataset survive a later correction.
    pin = next(pin for pin in manifest.input_revisions if pin.dataset == "player_profiles" and pin.record_key == (7,))
    previous = store.get("player_profiles", (7,), snapshot=snapshot(store))
    commit(store, correction(store, revision=previous.revision))
    retained = store.get("player_profiles", (7,), revision=pin.revision, snapshot=snapshot(store))
    assert retained.write.content_digest == pin.content_digest
    assert reproduce_dataset(store, "dev", manifest, artifacts).manifest == manifest
    bad = manifest.model_copy(update={"version":"invalid-pins", "input_revisions": (pin.model_copy(update={"content_digest":"0"*64}),)})
    with pytest.raises(ValueError, match="Manifest input"):
        commit(store, AcceptedBatch(batch_id=uuid4(),run_id=RUN,environment="dev", conflict_scopes=("dataset:datasets",),
            writes=(make_write("datasets",bad,expected_revision=None),)))


def test_full_consumer_behavior_matches_the_existing_populated_database(store, engine):
    from .pipeline_consumer_fixtures import populate
    from ml.pipelines.load_player_stats import PLAYER_SEASON_QUERY
    from ml.pipelines.load_salary_cap import SALARY_CAP_QUERY
    populate(engine, store)
    def responses(schema):
        with Session(engine) as session:
            session.execute(text(f"SET LOCAL search_path={schema},public"))
            service = TradeValueService(session)
            return [service.player_identity(1001), service.player_identity(1007),
                service.player_stats(1001,2025), service.player_stats(1006,2025),
                service.hockey_value(1001,2025), service.value_history(1001),
                service.contract(1001,2025), service.contract(1007,2025),
                service.teams(), service.team(102), service.roster(102,2025,"ACTIVE"),
                service.team_contracts(102,2025), service.team_cap(102,2025),
                service.search("Beta",["player","team"],8), service.leaders(2025,"C","BBB",5),
                service.overview(2025), service.compare([1001,1006],2025),
                service.players(2025,None,None,None,None,"points","desc",1,3),
                service.players(2025,"bbb","C","ACTIVE","High","name","asc",1,10),
                service.players(2025,None,None,None,"Low Forward","name","asc",1,10),
                [dict(row) for row in session.execute(PLAYER_SEASON_QUERY).mappings()],
                [dict(row) for row in session.execute(SALARY_CAP_QUERY).mappings() if row["season"]>=2008]]
    assert responses("pipeline_api") == responses("public")


def test_real_core_source_setup_then_event_driven_refresh_uses_durable_store(store):
    from .core_source_fixtures import SourceFixtures, runner, transaction
    from app.database_setup.run_setup import plan_setup, run_setup
    fixtures = SourceFixtures()
    fixtures.events = [transaction(day=datetime.now(timezone.utc).date().isoformat())]
    worker = runner(fixtures, store)
    worker.now = lambda: datetime.now(timezone.utc)
    selected = ("teams_seasons","player_profiles","team_rosters","source_id_mappings","basic_stats","contracts","transactions","roster_reconciliation")
    report = run_setup(worker, plan_setup(selected=selected, environment="dev",target_environment="dev",current_season=2026,first_season=2025))
    assert report.complete, [(item.run.job,item.error) for item in report.reports]
    assert worker.run(config("contracts",mode="refresh")).complete
    completions = store.scan(ReadRequest(dataset="refresh_completions",snapshot=snapshot(store))).records
    assert len(completions) == 1


def test_identity_transition_preserves_public_ids_and_never_overwrites_newer_profiles(store, engine):
    from database.pipeline.identities import bootstrap_identities, require_identity_transition
    from .core_source_fixtures import runner
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE players,teams RESTART IDENTITY CASCADE"))
        connection.execute(text("INSERT INTO players(id,first_name,last_name,active) VALUES (500,'Legacy','Name',true)"))
        connection.execute(text("INSERT INTO player_external_ids(player_id,source_id,external_id) SELECT 500,id,'1001' FROM data_sources WHERE code='nhl'"))
        connection.execute(text("INSERT INTO teams(id,nhl_team_id,abbreviation,name,active) VALUES (400,10,'TOR','Legacy Team',true)"))
    with pytest.raises(ValueError, match="bootstrap-identities"):
        require_identity_transition(store)
    bootstrap_identities(engine,"dev")
    require_identity_transition(store)
    worker = runner(store=store)
    worker.now = lambda:datetime.now(timezone.utc)
    assert worker.run(config("player_profiles")).complete
    profile = store.find_unique("player_profiles",("nhl_player_id",),(1001,),snapshot=snapshot(store))
    assert profile.write.decoded().player_id == 500
    assert profile.write.decoded().last_name == "Player 1001"
    bootstrap_identities(engine,"dev")
    assert store.get("player_profiles",(500,),snapshot=snapshot(store)).write.decoded().last_name == "Player 1001"
    assert store.find_unique("teams",("nhl_team_id",),(10,),snapshot=snapshot(store)).write.key == (400,)


def test_http_consumer_rejects_wrong_environment_and_missing_replacement_view(store, engine):
    import subprocess
    import sys
    from pathlib import Path
    def request(environment, path):
        child = {**os.environ, "ENV":environment, "DEV_DATABASE_URL":URL, "PROD_DATABASE_URL":URL,
            "DATA_QUERY_SCHEMA":"pipeline_api", "LOG_LEVEL":"ERROR", "PYTHONPATH":str(Path(__file__).resolve().parents[1])}
        script = "from fastapi.testclient import TestClient; from app.main import app; " + f"print(TestClient(app).get({path!r}).status_code)"
        result = subprocess.run([sys.executable,"-c",script],env=child,capture_output=True,text=True,timeout=20)
        assert result.returncode == 0, result.stderr
        return int(result.stdout.strip())
    assert request("dev","/api/health") == 200
    assert request("prod","/api/health") == 503
    with engine.begin() as connection:
        connection.execute(text("ALTER VIEW pipeline_api.players RENAME TO hidden_players"))
    try:
        # Missing replacement storage must fail rather than fall back to public.
        assert request("dev","/api/players/7") == 503
    finally:
        with engine.begin() as connection:
            connection.execute(text("ALTER VIEW pipeline_api.hidden_players RENAME TO players"))

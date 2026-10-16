"""Phase 7 orchestration on disposable PostgreSQL, with fresh adapters on resume."""
from datetime import datetime, timezone
import os

import pytest

from app.database_setup.run_setup import run_setup
from app.jobs import workflow
from app.jobs.shared.execution import Executor, JobOperation
from database.pipeline.store import PostgresStore
from .execution_fixtures import fixture_operations, config, batch, source, TEAM, SEASON
from .test_data_workflows import small_plan, audit_for
from .test_pipeline_persistence import engine, store

pytestmark = pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='Requires disposable PostgreSQL')


def test_manual_continuations_across_fresh_adapters_and_audited_final_gate(store, engine):
    worker = Executor(store, fixture_operations(), target_environment='dev')
    plan = small_plan()
    audit = audit_for(worker, plan)
    first, code = workflow.execute(worker, plan, max_partitions=1, audit=audit)
    assert code == 1 and first['continuation_required'] and first['processed_partitions'] == 1
    for expected in (2, 3):
        other = Executor(PostgresStore(engine, 'dev'), fixture_operations(), target_environment='dev')
        result, code = workflow.execute(other, small_plan(resume=True), max_partitions=1, audit=audit)
        assert result['processed_partitions'] == expected
    assert code == 0 and result['complete'] and result['coverage']['complete']
    assert not result['full_refill_complete']  # Selected fixture scope, not all history.


def test_final_gate_holds_union_reservation_across_independent_sessions(store, engine):
    worker = Executor(store, fixture_operations(), target_environment='dev')
    contender = Executor(PostgresStore(engine, 'dev'), fixture_operations(), target_environment='dev')
    checks = []
    def gate(report):
        assert report.complete
        checks.append(contender.run(config('player_profiles', mode='refresh')).run.status)
    assert run_setup(worker, small_plan(), finalize=gate).complete
    assert checks == ['deferred']
    assert contender.run(config('player_profiles', mode='refresh')).complete


def test_cancelled_refill_reports_non_success_and_resumes_only_committed_cursor(store, engine):
    def interrupted(ctx, cursor):
        yield batch(source('teams',TEAM),source('seasons',SEASON), cursor=1, final=False)
        raise KeyboardInterrupt()
    worker = Executor(store, {'teams_seasons':JobOperation(interrupted)}, target_environment='dev')
    plan = (config('teams_seasons'),)
    result, code = workflow.execute(worker, plan, max_partitions=1)
    assert code == 130 and result['runs'][0]['run']['status'] == 'cancelled'
    seen = []
    def resumed(ctx, cursor):
        seen.append(cursor)
        yield batch(cursor=2, final=True)
    fresh = Executor(PostgresStore(engine,'dev'), {'teams_seasons':JobOperation(resumed)}, target_environment='dev')
    resumed_plan = (config('teams_seasons',resume=True),)
    audit = audit_for(fresh, resumed_plan)
    result, code = workflow.execute(fresh, resumed_plan, max_partitions=1, audit=audit)
    assert code == 0 and result['complete'] and seen == [1]
    snapshot = store.snapshot('dev',accepted_before=datetime.now(timezone.utc))
    assert store.get('teams',(10,),snapshot=snapshot).revision == 1

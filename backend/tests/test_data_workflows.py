"""Workflow policy, safe scope selection, durable continuation and final evidence."""
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.database_setup.run_setup import plan_setup, run_setup
from app.database_setup.validate_setup import setup_partitions
from app.jobs import workflow
from app.jobs.shared.configuration import JOBS
from .execution_fixtures import executor, fixture_operations, config

SCRIPTS = Path(__file__).resolve().parents[2] / '.github/scripts'
sys.path.insert(0, str(SCRIPTS))
from data_workflow_guard import approve
from validate_data_workflows import validate

SHA = 'a' * 40
TARGET = str(uuid4())
BASE = {'DATA_ENVIRONMENT': 'nonprod', 'DATA_TARGET_ID': TARGET,
        'DATA_REQUESTED_TARGET': TARGET, 'DATA_APPROVED_SHA': SHA,
        'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REF': 'refs/heads/Release-1.1.0',
        'GITHUB_SHA': SHA}


def options(**changes):
    return {'DATA_JOB': 'refill', 'DATA_ENVIRONMENT': 'nonprod',
            'DATA_VALIDATION_ONLY': 'false', **changes}


def small_plan(resume=False, dry=False):
    return plan_setup(selected=tuple(fixture_operations()), environment='dev', target_environment='dev',
        current_season=2026, first_season=2026, resume=resume, mode='validation' if dry else 'initial')


def audit_for(worker, plan):
    # Independent fixture population declared before collection, never copied
    # from accepted rows. Production audit files come from upstream audits.
    worker.store.target_id = getattr(worker.store, 'target_id', TARGET)
    keys = {'teams': [[10]], 'seasons': [[2026]], 'player_profiles': [[7]], 'memberships': [[1]]}
    return {'target_id': worker.store.target_id, 'audit_reference': 'independent fixture manifest',
            'scope': {'current_season': 2026, 'first_season': 2026, 'last_season': 2026, 'game_types': [2, 3]},
            'partitions': [{'dataset': p.dataset, 'season': p.season, 'game_type': p.game_type,
                            'expected_keys': keys[p.dataset]} for p in setup_partitions(plan)]}


def test_repository_workflows_and_generated_defaults_match():
    assert validate() == 15
    from generate_data_workflows import render
    root = SCRIPTS.parents[1]
    defaults = json.loads((root / '.github/data-jobs.json').read_text())
    assert set(defaults) == set(JOBS)
    for job, settings in [*defaults.items(), ('refill', {})]:
        filename, expected = render(job, settings)
        assert (root / '.github/workflows' / filename).read_text() == expected


@pytest.mark.parametrize('mutation', ('schedule', 'auto-caller', 'local-caller', 'python-caller', 'cancel', 'credential-order'))
def test_policy_rejects_accidental_refill_activation(tmp_path, mutation):
    root = SCRIPTS.parents[1]
    shutil.copytree(root / '.github', tmp_path / '.github')
    path = tmp_path / '.github/workflows/database-refill.yml'
    text = path.read_text()
    if mutation == 'schedule':
        text = text.replace('on:\n', "on:\n  schedule:\n    - cron: '0 * * * *'\n", 1)
    elif mutation == 'auto-caller':
        (tmp_path / '.github/workflows/unsafe.yml').write_text('run: gh workflow run database-refill.yml\n')
    elif mutation == 'local-caller':
        (tmp_path / '.github/workflows/unsafe.yml').write_text('uses: ./.github/workflows/database-refill.yml\n')
    elif mutation == 'python-caller':
        (tmp_path / '.github/scripts/unsafe.py').write_text('command = "gh workflow run database-refill.yml"\n')
    elif mutation == 'cancel':
        text = text.replace('cancel-in-progress: false', 'cancel-in-progress: true')
    else:
        text = text.replace('run: python3 .github/scripts/data_workflow_guard.py', 'run: echo ${{ secrets.DATABASE_URL }}')
    path.write_text(text)
    with pytest.raises(AssertionError):
        validate(tmp_path)


@pytest.mark.parametrize('changes', (
    {'GITHUB_REF': 'refs/heads/Dev'}, {'GITHUB_SHA': 'b' * 40},
    {'DATA_REQUESTED_TARGET': str(uuid4())}, {'DATA_APPROVED_SHA': 'Prod'},
    {'DATA_ENVIRONMENT': 'dev'}, {'GITHUB_EVENT_NAME': 'push'},
    {'DATA_TARGET_ID': 'not-a-uuid'},
))
def test_dispatch_guard_rejects_unapproved_code_environment_and_target(changes):
    with pytest.raises(ValueError):
        approve({**BASE, **changes}, ['Dev', 'Release-1.1.0', 'Prod'], SHA)


def test_guard_accepts_promoted_immutable_code_and_fail_closes_after_promotion():
    assert approve(BASE, ['Dev', 'Release-1.1.0', 'Prod'], SHA) == SHA
    assert approve({**BASE, 'DATA_ENVIRONMENT': 'prod', 'GITHUB_REF': 'refs/heads/Prod'}, ['Prod'], SHA) == SHA
    with pytest.raises(ValueError):
        approve(BASE, ['Release-1.1.0', 'Release-1.2.0'], SHA)
    with pytest.raises(ValueError):
        approve(BASE, ['Release-1.1.0'], 'b' * 40)


@pytest.mark.parametrize('environment,enabled,ok', (('nonprod','true',True), ('prod','true',False), ('nonprod','',False), ('nonprod','false',False)))
def test_schedule_cannot_target_production(environment, enabled, ok):
    values = {**BASE, 'DATA_ENVIRONMENT': environment, 'GITHUB_EVENT_NAME': 'schedule',
              'DATA_NONPROD_SCHEDULES_ENABLED': enabled, 'DATA_NOTIFICATION_OWNER': 'maintainer'}
    if ok:
        assert approve(values, ['Release-1.1.0'], SHA) == SHA
    else:
        with pytest.raises(ValueError):
            approve(values, ['Release-1.1.0'], SHA)


def test_default_refill_scope_preserves_history_and_current_only_jobs():
    plan, maximum = workflow.make_plan(options(), 2026)
    assert maximum == 8
    assert {c.job for c in plan} == set(JOBS) - {'datasets'}
    for job, spec in JOBS.items():
        if job == 'datasets':
            continue
        partitions = [c for c in plan if c.job == job]
        assert partitions[0].first_season == 2026
        assert partitions[-1].first_season == (2026 if spec.current_only else spec.history_start)
        assert all(c.game_types == (2, 3) for c in partitions)
    names = [c.job for c in plan]
    assert names.index('teams_seasons') < names.index('game_schedule') < names.index('game_details')


@pytest.mark.parametrize('changes', ({'DATA_MAX_PARTITIONS': '0'}, {'DATA_MAX_PARTITIONS': '1001'},
    {'DATA_JOBS': 'unknown'}, {'DATA_ENVIRONMENT': 'dev'}, {'DATA_FIRST_SEASON': '2007'},
    {'DATA_VALIDATION_ONLY': 'yes'}, {'DATA_VALIDATION_ONLY': 'true', 'DATA_RESUME': 'true'},
    {'DATA_LAST_SEASON': '2020'}))
def test_invalid_refill_scope_is_rejected(changes):
    with pytest.raises(ValueError):
        workflow.make_plan(options(**changes), 2026)


def test_independent_refresh_controls_and_current_only_transaction_bounds():
    plan, maximum = workflow.make_plan(options(DATA_JOB='game_details', DATA_LOOKBACK_DAYS='14',
        DATA_MAX_INPUT_AGE_SECONDS='3600', DATA_MAX_BATCHES='5', DATA_ENABLED='false'), 2026)
    assert maximum is None
    assert plan[0].first_season == plan[0].last_season == 2026
    assert (plan[0].correction_lookback_days, plan[0].max_input_age_seconds, plan[0].max_batches) == (14,3600,5)
    assert not plan[0].enabled
    with pytest.raises(ValueError):
        workflow.make_plan(options(DATA_JOB='transactions', DATA_LOOKBACK_DAYS='32'), 2026)
    with pytest.raises(ValueError):
        workflow.make_plan(options(DATA_JOB='transactions', DATA_FIRST_SEASON='2025'), 2026)
    with pytest.raises(ValueError):
        workflow.make_plan(options(DATA_JOB='game_details', DATA_RESUME='true'), 2026)


def test_source_resolves_current_season_without_calendar_guess():
    assert workflow.current_season(SimpleNamespace(json=lambda *_: {'standings':[{'seasonId':20262027}]})) == 2026
    for rows in ([], [{'seasonId':20252026},{'seasonId':20262027}]):
        with pytest.raises(ValueError):
            workflow.current_season(SimpleNamespace(json=lambda *_: {'standings':rows}))


def test_manual_partition_continuations_do_not_repeat_the_same_quota():
    worker = executor()
    first = run_setup(worker, small_plan(), max_partitions=1)
    assert not first.complete and len(first.reports) == 1
    second = run_setup(worker, small_plan(resume=True), max_partitions=1)
    assert not second.complete and len(second.reports) == 2
    assert second.reports[0].run.status == 'no_change'
    third = run_setup(worker, small_plan(resume=True), max_partitions=1)
    assert third.complete
    assert [r.run.status for r in third.reports[:2]] == ['no_change','no_change']


def test_refill_final_gate_requires_independent_population_and_labels_partial_scope():
    worker = executor()
    plan = small_plan()
    audit = audit_for(worker, plan)
    payload, code = workflow.execute(worker, plan, max_partitions=8, audit=audit)
    assert code == 0 and payload['complete']
    assert payload['kind'] == 'selected_backfill' and not payload['full_refill_complete']
    payload, code = workflow.execute(worker, small_plan(resume=True), max_partitions=8)
    assert code == 1 and not payload['complete']
    assert all(issue['code'] == 'NOT_PROCESSED' for issue in payload['coverage']['issues'])


def test_extra_missing_or_duplicate_population_cannot_pass_final_gate():
    worker = executor()
    plan = small_plan()
    audit = audit_for(worker, plan)
    run_setup(worker, plan)
    report = run_setup(worker, small_plan(resume=True))
    for key in ([[999]], [], [[10], [999]]):
        bad = {**audit, 'partitions': [{**e, 'expected_keys': key} if e['dataset'] == 'teams' else e for e in audit['partitions']]}
        assert not workflow.coverage_gate(worker, report, bad)['complete']
    duplicate = {**audit, 'partitions': [audit['partitions'][0]] * 2}
    with pytest.raises(ValueError):
        workflow.coverage_gate(worker, report, duplicate)
    with pytest.raises(ValueError):
        workflow.coverage_gate(worker, report, {**audit, 'target_id':str(uuid4())})


def test_entire_refill_reservation_includes_unprocessed_partitions_and_final_gate():
    worker = executor()
    checked = []
    def finalize(report):
        contender = worker.run(config('player_profiles', mode='refresh'))
        checked.append(contender.run.status)
    run_setup(worker, small_plan(), finalize=finalize)
    # ContractStore models conflicts; actual independent sessions tested below.
    assert checked == ['deferred']
    assert worker.run(config('player_profiles', mode='refresh')).complete


def test_validation_only_does_not_commit_progress_or_claim_full_refill():
    worker = executor()
    payload, code = workflow.execute(worker, small_plan(dry=True), max_partitions=8)
    assert worker.store.rows == {} and worker.store.checkpoints == {}
    assert payload['validation_only'] and not payload['full_refill_complete']
    assert code == 1  # No independent accepted-population evidence in an empty DB.


def test_configuration_paths_cannot_escape_approved_checkout(tmp_path):
    with pytest.raises(ValueError):
        workflow.approved_file('/etc/passwd')
    with pytest.raises(ValueError):
        workflow.approved_file('../secrets.json')


def test_dataset_publication_rejects_ephemeral_runner_storage(monkeypatch, tmp_path):
    cfg = tmp_path / 'dataset.json'
    cfg.write_text('{}')
    monkeypatch.setattr(workflow, 'approved_file', lambda _:cfg)
    values = {'DATA_DATASET_CONFIG':'config.json', 'DATA_ARTIFACT_ROOT':str(tmp_path / 'artifacts'),
              'GITHUB_WORKSPACE':str(tmp_path), 'RUNNER_TEMP':str(tmp_path)}
    with pytest.raises(ValueError):
        workflow.prepare_dataset_config(values, False)
    with pytest.raises(ValueError):
        workflow.prepare_dataset_config(values, True)


def test_invalid_runtime_is_sanitized_and_disabled_never_connects(monkeypatch, capsys, tmp_path):
    import database.pipeline.runtime as runtime
    monkeypatch.setattr(workflow, 'ROOT', tmp_path)
    monkeypatch.setenv('DATA_ENVIRONMENT', 'nonprod')
    monkeypatch.setenv('DATA_JOB', 'teams_seasons')
    monkeypatch.setenv('DATA_VALIDATION_ONLY', 'true')
    monkeypatch.setenv('DATA_ENABLED', 'false')
    def fail(_):
        raise ValueError('postgresql://secret:password@host/private')
    monkeypatch.setattr(runtime,'create_runtime',fail)
    assert workflow.main() == 4
    monkeypatch.setenv('DATA_ENABLED','true')
    assert workflow.main() == 2
    output = capsys.readouterr()
    assert 'password' not in output.out + output.err
    payload = json.loads((tmp_path / 'coverage/data-workflow/report.json').read_text())
    assert payload['reason_code'] == 'INVALID_CONFIGURATION'


def test_runner_uses_existing_entrypoints_through_three_manual_continuations(monkeypatch, tmp_path):
    from app.jobs.shared.execution import Executor
    from .contract_store import ContractStore
    import database.pipeline.runtime as runtime
    worker = Executor(ContractStore(), fixture_operations(), target_environment='nonprod')
    worker.store.target_id = TARGET
    worker.store.engine = SimpleNamespace(dispose=lambda:None)
    plan, _ = workflow.make_plan(options(DATA_JOBS='teams_seasons player_profiles team_rosters',
        DATA_FIRST_SEASON='2026'),2026)
    audit = audit_for(worker, plan)
    path = tmp_path / 'audit.json'
    path.write_text(json.dumps(audit))
    monkeypatch.setattr(workflow,'ROOT',tmp_path)
    monkeypatch.setattr(workflow,'approved_file',lambda _:path)
    monkeypatch.setattr(runtime,'create_runtime',lambda _:worker)
    monkeypatch.setenv('PIPELINE_DATASET_CONFIG','/ambient/unapproved-config.json')
    for key,value in options(DATA_JOB='refill', DATA_TARGET_ID=TARGET, DATA_CURRENT_SEASON='2026',
        DATA_FIRST_SEASON='2026', DATA_JOBS='teams_seasons player_profiles team_rosters',
        DATA_COVERAGE_CONFIG='audit.json', DATA_MAX_PARTITIONS='1', DATA_RESUME='false', DATA_ENABLED='true',
        GITHUB_STEP_SUMMARY=str(tmp_path / 'summary.md')).items():
        monkeypatch.setenv(key,value)
    assert workflow.main() == 1
    monkeypatch.setenv('DATA_RESUME','true')
    assert workflow.main() == 1
    assert workflow.main() == 0
    result = json.loads((tmp_path / 'coverage/data-workflow/report.json').read_text())
    assert result['complete'] and not result['continuation_required']
    assert 'Accepted | Rejected | Unresolved' in (tmp_path / 'summary.md').read_text()
    import os
    assert os.environ['PIPELINE_DATASET_CONFIG'] == ''


def test_dataset_job_and_refill_use_selected_audited_dataset_scope(monkeypatch, tmp_path):
    path = tmp_path / 'dataset.json'
    path.write_text(json.dumps({'first_season':2020,'last_season':2023}))
    monkeypatch.setattr(workflow,'approved_file',lambda _:path)
    plan, _ = workflow.make_plan(options(DATA_JOB='datasets',DATA_DATASET_CONFIG='dataset.json'),2026)
    assert (plan[0].first_season,plan[0].last_season,plan[0].game_types) == (2020,2023,(2,))
    refill, _ = workflow.make_plan(options(DATA_DATASET_CONFIG='dataset.json'),2026)
    assert refill[-1].job == 'datasets'
    assert (refill[-1].first_season,refill[-1].last_season,refill[-1].game_types) == (2020,2023,(2,))
    with pytest.raises(ValueError):
        workflow.make_plan(options(DATA_DATASET_CONFIG='dataset.json',DATA_FIRST_SEASON='2021'),2026)


def test_schedule_requires_an_assigned_notification_owner():
    with pytest.raises(ValueError):
        approve({**BASE,'GITHUB_EVENT_NAME':'schedule','DATA_NONPROD_SCHEDULES_ENABLED':'true'},
                ['Release-1.1.0'],SHA)


def test_large_population_audits_use_independent_count_and_sorted_key_digest():
    from hashlib import sha256
    from app.jobs.shared.data_contracts import canonical_json
    worker = executor()
    plan = small_plan()
    audit = audit_for(worker, plan)
    partitions = []
    for entry in audit['partitions']:
        keys = sorted(canonical_json(key) for key in entry['expected_keys'])
        partitions.append({**{k:v for k,v in entry.items() if k != 'expected_keys'},
                           'expected_count':len(keys),
                           'expected_key_digest':sha256(b''.join(key+b'\n' for key in keys)).hexdigest()})
    audit['partitions'] = partitions
    report = run_setup(worker, plan)
    assert workflow.coverage_gate(worker,report,audit)['complete']
    audit['partitions'][0]['expected_key_digest'] = '0' * 64
    assert not workflow.coverage_gate(worker,report,audit)['complete']

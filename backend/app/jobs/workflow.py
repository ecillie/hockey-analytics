"""Thin GitHub/local orchestration around existing named jobs and setup.

No source parsing, schema preparation, dispatching, or scheduler activation.
"""
from importlib import import_module
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import UUID

from app.database_setup.run_setup import plan_setup, run_setup
from app.database_setup.validate_setup import setup_partitions, validate_setup
from app.jobs.shared.cli import console_report, report_exit_code
from app.jobs.shared.configuration import JOBS, JobConfig
from app.jobs.shared.coverage import CoverageObservation, CoveragePartition
from app.jobs.shared.access_contracts import ReadRequest
from app.jobs.shared.data_contracts import RECORD_DEFINITIONS, canonical_json

ROOT = Path(__file__).resolve().parents[3]


def boolean(value):
    if value not in ('true', 'false'):
        raise ValueError('Boolean inputs must be explicit')
    return value == 'true'


def approved_file(value):
    path = (ROOT / value).resolve()
    if not value or not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError('Configuration must be a file in the approved checkout')
    return path


def current_season(client):
    """Resolve the source's current season, including offseason boundary behavior."""
    from app.jobs.sources.nhl import WEB, season_year
    rows = client.json('nhl', f'{WEB}/standings/now')['standings']
    years = {season_year(row['seasonId']) for row in rows}
    if len(years) != 1:
        raise ValueError('Current NHL season could not be resolved')
    return years.pop()


def make_plan(values, current):
    job = values['DATA_JOB']
    environment = values['DATA_ENVIRONMENT']
    if environment not in ('nonprod', 'prod'):
        raise ValueError('Workflows require an explicit nonprod/prod target')
    dry = boolean(values.get('DATA_VALIDATION_ONLY', 'true'))
    resume = boolean(values.get('DATA_RESUME', 'false'))
    first = int(values.get('DATA_FIRST_SEASON') or (2008 if job == 'refill' else current))
    last = int(values.get('DATA_LAST_SEASON') or current)
    dataset_scope = None
    if values.get('DATA_DATASET_CONFIG') and (job == 'datasets' or
            (job == 'refill' and ('datasets' in values.get('DATA_JOBS', '').split() or not values.get('DATA_JOBS')))):
        dataset_scope = json.loads(approved_file(values['DATA_DATASET_CONFIG']).read_text())
        if job == 'datasets':
            first = int(values.get('DATA_FIRST_SEASON') or dataset_scope['first_season'])
            last = int(values.get('DATA_LAST_SEASON') or dataset_scope['last_season'])
    if job == 'refill':
        selected = tuple(values.get('DATA_JOBS', '').split()) or tuple(
            name for name in JOBS if name != 'datasets' or values.get('DATA_DATASET_CONFIG'))
        if dry and resume:
            raise ValueError('Validation-only cannot resume write checkpoints')
        plan = plan_setup(selected=selected, environment=environment, target_environment=environment,
            current_season=current, first_season=first, last_season=last,
            mode='validation' if dry else 'initial', resume=resume)
        plan = tuple(JobConfig(**{**config.model_dump(),
            'max_batches': int(values.get('DATA_MAX_BATCHES') or 10000),
            **({'first_season': dataset_scope['first_season'], 'last_season': dataset_scope['last_season'],
                'game_types': (2,)} if config.job == 'datasets' and dataset_scope else {})}) for config in plan)
        if dataset_scope and not first <= dataset_scope['first_season'] <= dataset_scope['last_season'] <= last:
            raise ValueError('Dataset range must fit the refill range')
        maximum = int(values.get('DATA_MAX_PARTITIONS') or 8)
        if not 1 <= maximum <= 1000:
            raise ValueError('Partition budget must be 1-1000')
        return plan, maximum
    if job not in JOBS or resume:
        raise ValueError('Refresh jobs do not resume initial-load checkpoints')
    defaults = json.loads((ROOT / '.github/data-jobs.json').read_text())[job]
    options = dict(defaults)
    for name, variable in [('correction_lookback_days', 'DATA_LOOKBACK_DAYS'),
                           ('max_input_age_seconds', 'DATA_MAX_INPUT_AGE_SECONDS')]:
        if values.get(variable):
            options[name] = int(values[variable])
    enabled = boolean(values.get('DATA_ENABLED') or str(options['enabled']).lower())
    config = JobConfig(job=job, environment=environment, target_environment=environment,
        mode='validation' if dry else 'refresh', current_season=current,
        first_season=first, last_season=last, enabled=enabled,
        correction_lookback_days=options['correction_lookback_days'],
        max_input_age_seconds=options['max_input_age_seconds'],
        game_types=(2,) if job == 'datasets' else (2, 3),
        max_batches=int(values.get('DATA_MAX_BATCHES') or 10000))
    # USA Today supports recent windows only, including manual dispatch.
    if job == 'transactions' and not 1 <= config.correction_lookback_days <= 31:
        raise ValueError('Transactions require a 1-31 day lookback')
    return (config,), None


def rows(reader, dataset, snapshot, filters=None):
    cursor, seen = None, set()
    while True:
        page = reader.scan(ReadRequest(dataset=dataset, snapshot=snapshot, cursor=cursor,
            scope_json=canonical_json(filters or {})))
        if page.snapshot != snapshot:
            raise ValueError('Coverage read changed its snapshot')
        yield from page.records
        cursor = page.next_cursor
        if cursor is None:
            return
        if cursor in seen:
            raise ValueError('Coverage cursor repeated')
        seen.add(cursor)


def coverage_gate(executor, report, audit):
    """Compare accepted identities to an independently audited exact population.

    Never infer expected coverage from the rows that happened to load. Optional
    partitions can remain unaudited, and are reported by validate_setup.
    """
    partitions = setup_partitions(report.requested)
    current = report.requested[0].current_season
    scope = {'current_season': current,
             'first_season': min(c.first_season for c in report.requested),
             'last_season': max(c.last_season for c in report.requested), 'game_types': [2, 3]}
    if not audit:
        complete, result = validate_setup(report, partitions, (), current_season=current)
    else:
        if (audit['scope'] != scope or not audit['audit_reference'].strip()
                or audit['target_id'] != executor.store.target_id):
            raise ValueError('Coverage audit differs from target/scope')
        snapshot = executor.store.snapshot(executor.target_environment, accepted_before=executor.now())
        observations, seen = [], set()
        for entry in audit['partitions']:
            partition = CoveragePartition(entry['dataset'], entry.get('season'), entry.get('game_type'))
            if partition not in partitions or partition in seen:
                raise ValueError('Audit has duplicate/out-of-scope partitions')
            seen.add(partition)
            actual = set()
            fields = RECORD_DEFINITIONS[partition.dataset].model.model_fields
            filters = {name: value for name, value in (('season', partition.season), ('game_type', partition.game_type))
                       if value is not None and name in fields}
            for stored in rows(executor.store, partition.dataset, snapshot, filters):
                record = stored.write.decoded()
                season = getattr(record, 'season', None)
                game_type = getattr(record, 'game_type', None)
                if partition.season is not None and season is None and hasattr(record, 'game_id'):
                    game = executor.store.get('games', (record.game_id,), snapshot=snapshot)
                    if game is None:
                        raise ValueError('Coverage record lacks its game reference')
                    season, game_type = game.write.decoded().season, game.write.decoded().game_type
                if ((partition.season is None or partition.season == season)
                        and (partition.game_type is None or partition.game_type == game_type)):
                    actual.add(canonical_json(list(stored.write.key)))
            if 'expected_keys' in entry:
                expected = {canonical_json(key) for key in entry['expected_keys']}
                if len(expected) != len(entry['expected_keys']):
                    raise ValueError('Audit has duplicate expected identities')
                expected_count, accepted_count = len(expected), len(actual & expected)
                invalid, matches = len(actual - expected), actual == expected
            else:
                expected_count = entry['expected_count']
                digest = entry['expected_key_digest']
                if (type(expected_count) is not int or expected_count < 0 or not isinstance(digest, str)
                        or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)):
                    raise ValueError('Invalid independently audited population count/digest')
                actual_digest = sha256()
                for key in sorted(actual):
                    actual_digest.update(key + b'\n')
                matches = expected_count == len(actual) and digest == actual_digest.hexdigest()
                accepted_count = min(expected_count, len(actual))
                invalid = max(0, len(actual) - expected_count)
            observations.append(CoverageObservation(partition, expected_count, accepted_count,
                collection_complete=report.complete and matches, invalid_records=invalid))
        complete, result = validate_setup(report, partitions, observations, current_season=current)
    return {'complete': complete, 'policy_version': result.policy_version,
            'requested_partitions': len(partitions),
            'issues': [{'dataset': issue.partition.dataset, 'season': issue.partition.season,
                        'game_type': issue.partition.game_type, 'code': issue.code,
                        'blocking': issue.blocking} for issue in result.issues]}


def execute(executor, plan, *, max_partitions=None, audit=None):
    if max_partitions is None:
        config = plan[0]
        report = import_module(f'app.jobs.{config.job}').run(executor, config)
        return {'complete': report.complete, 'kind': 'refresh', 'runs': [console_report(report)]}, report_exit_code(report)
    gate = {}
    def finalize(report):
        gate.update(coverage_gate(executor, report, audit))
    report = run_setup(executor, plan, max_partitions=max_partitions, finalize=finalize)
    required = set(JOBS) - {'datasets'}
    full_scope = (required <= {config.job for config in plan}
                  and min(config.first_season for config in plan) == 2008
                  and max(config.last_season for config in plan) == plan[0].current_season)
    complete = report.complete and gate.get('complete', False)
    payload = {'complete': complete, 'kind': 'full_refill' if full_scope else 'selected_backfill',
               'full_refill_complete': complete and full_scope and plan[0].mode != 'validation',
               'validation_only': plan[0].mode == 'validation',
               'requested_partitions': len(plan), 'processed_partitions': len(report.reports),
               'continuation_required': not report.complete,
               'coverage': gate or {'complete': False, 'reason_code': 'POPULATION_INCOMPLETE'},
               'runs': [console_report(item) for item in report.reports]}
    code = 0 if complete else next((report_exit_code(item) for item in report.reports if not item.complete), 1)
    return payload, code


def prepare_dataset_config(values, dry):
    """Runners may only publish manifests pointing at retained mounted artifacts."""
    value = values.get('DATA_DATASET_CONFIG')
    if not value:
        return
    config = json.loads(approved_file(value).read_text())
    artifact_root = Path(values.get('DATA_ARTIFACT_ROOT') or '')
    if not artifact_root.is_absolute():
        raise ValueError('Dataset builds require an explicit artifact root')
    root = artifact_root.resolve()
    if not dry and not any(path != Path('/') and path.is_mount() for path in (root, *root.parents)):
        raise ValueError('Dataset publication requires a retained mounted artifact store')
    for transient in ('GITHUB_WORKSPACE', 'RUNNER_TEMP'):
        if values.get(transient) and root.is_relative_to(Path(values[transient]).resolve()):
            raise ValueError('Dataset artifacts cannot live in a transient runner directory')
    config['artifact_root'] = str(root)
    output = Path(values.get('RUNNER_TEMP') or '/tmp') / 'tradevalue-dataset-config.json'
    output.write_text(json.dumps(config))
    os.environ['PIPELINE_DATASET_CONFIG'] = str(output)


def write_result(payload, code, values):
    output = ROOT / 'coverage/data-workflow/report.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    payload['exit_code'] = code
    output.write_text(json.dumps(payload, indent=2) + '\n')
    summary = values.get('GITHUB_STEP_SUMMARY')
    if summary:
        with Path(summary).open('a') as stream:
            stream.write(f'## Data workflow\n\n- Complete: {payload.get("complete", False)}\n'
                         f'- Exit code: {code}\n- See sanitized report artifact and database run records.\n')
            stream.write('\n| Job | Status | Accepted | Rejected | Unresolved |\n'
                         '| --- | --- | ---: | ---: | ---: |\n')
            for item in payload.get('runs', ()):
                run = item['run']
                counts = run['counters']
                stream.write(f'| {run["job"]} | {run["status"]} | {counts["accepted"]} | '
                             f'{counts["rejected"]} | {counts["unresolved"]} |\n')
            if payload.get('coverage'):
                stream.write(f'\nFinal coverage complete: {payload["coverage"]["complete"]}.\n')
    print(json.dumps(payload))


def main():
    from app.jobs.shared.cli import configure_cli
    from app.observability import configure_logging, log_event
    from database.pipeline.runtime import create_runtime
    import logging
    import signal
    configure_cli()
    values = dict(os.environ)
    code, payload = 2, {'complete': False, 'reason_code': 'INVALID_CONFIGURATION'}
    executor = None
    # GNU timeout sends INT first so the existing executor saves a terminal run
    # and releases its session; SIGKILL remains the fallback for blocked I/O.
    def interrupt(*_):
        raise KeyboardInterrupt()
    previous_handler = signal.signal(signal.SIGTERM, interrupt)
    try:
        environment = values['DATA_ENVIRONMENT']
        configure_logging(environment=environment)
        dry = boolean(values.get('DATA_VALIDATION_ONLY', 'true'))
        enabled = values.get('DATA_ENABLED')
        if not enabled:
            enabled = 'true' if values['DATA_JOB'] == 'refill' else str(
                json.loads((ROOT / '.github/data-jobs.json').read_text())[values['DATA_JOB']]['enabled']).lower()
        if not boolean(enabled):
            write_result({'complete': False, 'reason_code': 'DISABLED'}, 4, values)
            return 4
        if values['DATA_JOB'] not in ('datasets', 'refill') or (values['DATA_JOB'] == 'refill'
                and values.get('DATA_JOBS') and 'datasets' not in values['DATA_JOBS'].split()):
            values.pop('DATA_DATASET_CONFIG', None)
        prepare_dataset_config(values, dry)
        # Explicitly prevent ambient backend/.env dataset configuration from being used.
        if not values.get('DATA_DATASET_CONFIG'):
            os.environ['PIPELINE_DATASET_CONFIG'] = ''
        executor = create_runtime(environment)
        if str(UUID(values['DATA_TARGET_ID'])) != executor.store.target_id:
            raise ValueError('Prepared database target differs')
        current = int(values['DATA_CURRENT_SEASON']) if values.get('DATA_CURRENT_SEASON') else current_season(executor.client)
        plan, maximum = make_plan(values, current)
        scope = {'current_season': current, 'first_season': min(c.first_season for c in plan),
                 'last_season': max(c.last_season for c in plan), 'partitions': len(plan),
                 'game_types': [2] if values['DATA_JOB'] == 'datasets' else [2, 3]}
        print(json.dumps({'requested_scope': scope, 'validation_only': dry}), flush=True)
        audit = json.loads(approved_file(values['DATA_COVERAGE_CONFIG']).read_text()) if values.get('DATA_COVERAGE_CONFIG') else None
        payload, code = execute(executor, plan, max_partitions=maximum, audit=audit)
        payload['scope'] = scope
    except KeyboardInterrupt:
        code, payload = 130, {'complete': False, 'reason_code': 'CANCELLED', 'continuation_required': True}
    except Exception as exc:
        log_event(logging.getLogger(__name__), 'cli.failed', level=logging.ERROR, error=exc)
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
        if executor is not None:
            executor.store.engine.dispose()
    write_result(payload, code, values)
    return code


if __name__ == '__main__':
    raise SystemExit(main())

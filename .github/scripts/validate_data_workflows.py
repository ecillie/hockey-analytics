#!/usr/bin/env python3
"""Repository policy checks complement actionlint's GitHub syntax/type checks."""
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]


def validate(root=ROOT):
    workflows = root / '.github/workflows'
    configs = json.loads((root / '.github/data-jobs.json').read_text())
    expected = {'database-refill.yml', 'data-dataset-build.yml'} | {
        f'data-update-{job.replace("_", "-")}.yml' for job in configs if job != 'datasets'}
    actual = {path.name for path in workflows.glob('data-*.yml')} | {'database-refill.yml'}
    assert actual == expected, 'Missing/unexpected data workflow'
    for filename in expected:
        content = (workflows / filename).read_text()
        data = yaml.load(content, Loader=yaml.BaseLoader)
        events = data['on']
        refill = filename == 'database-refill.yml'
        assert set(events) == ({'workflow_dispatch'} if refill else {'schedule', 'workflow_dispatch'})
        inputs = events['workflow_dispatch']['inputs']
        assert inputs['environment']['options'] == ['nonprod', 'prod']
        assert inputs['target_id']['required'] == 'true'
        assert inputs['validation_only']['default'] == 'true'
        assert data['permissions'] == {'contents': 'read'}
        assert data['concurrency']['cancel-in-progress'] == 'false'
        job = data['jobs']['execute']
        assert "inputs.environment || 'nonprod'" in job['environment']
        assert job['timeout-minutes'] == '330'
        if not refill:
            assert "vars.DATA_NONPROD_SCHEDULES_ENABLED == 'true'" in job['if']
        steps = job['steps']
        guard = next(i for i, step in enumerate(steps) if step.get('id') == 'guard')
        runner = next(i for i, step in enumerate(steps) if step.get('uses') == './.github/actions/data-job')
        assert guard < runner
        assert steps[guard + 1]['with']['ref'] == '${{ steps.guard.outputs.sha }}'
        assert all('secrets.DATABASE_URL' not in str(step) for step in steps[:runner])
        assert steps[runner]['with']['job'] == ('refill' if refill else 'datasets' if filename == 'data-dataset-build.yml' else filename[12:-4].replace('-', '_'))
        assert '${{' not in str([step.get('run', '') for step in steps]), 'Untrusted shell interpolation'
        artifact = steps[-1]
        assert artifact['with']['path'] == 'coverage/data-workflow/report.json'
        assert artifact['with']['retention-days'] == '14'
    # No workflow, action or helper may auto-dispatch a refill continuation.
    for folder in (root / '.github/workflows', root / '.github/actions', root / '.github/scripts'):
        for path in folder.rglob('*'):
            if path.suffix not in ('.yml', '.yaml', '.sh', '.py') or path.name == Path(__file__).name:
                continue
            source = path.read_text()
            if path.name != 'database-refill.yml':
                assert not re.search(r'(workflow run|dispatches|workflow_call|createWorkflowDispatch).*database-refill|database-refill.*(workflow_call|dispatches|createWorkflowDispatch)', source)
                assert not re.search(r'uses:\s*[\'\"]?\S*database-refill\.ya?ml', source)
    return len(expected)


if __name__ == '__main__':
    subprocess.run([sys.executable, str(ROOT / '.github/scripts/generate_data_workflows.py'), '--check'], check=True)
    print(f'{validate()} data workflows satisfy repository policy')

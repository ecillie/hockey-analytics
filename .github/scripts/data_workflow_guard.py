#!/usr/bin/env python3
"""Credential-free guard for dispatch/schedule code selection. Fail closed."""
import json
import os
from pathlib import Path
import re
import subprocess
from uuid import UUID

from latest_release_branch import latest_release_branch


def approve(values, branches, branch_sha):
    environment = values['DATA_ENVIRONMENT']
    event = values['GITHUB_EVENT_NAME']
    target = values['DATA_TARGET_ID']
    UUID(target)
    sha = values['DATA_APPROVED_SHA']
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('An immutable approved SHA is required')
    if environment not in ('nonprod', 'prod'):
        raise ValueError('Select an explicit environment')
    branch = 'Prod' if environment == 'prod' else latest_release_branch(branches)
    if branch_sha != sha:
        raise ValueError('Promoted branch head differs from the approved SHA')
    if event == 'schedule':
        if environment != 'nonprod' or values.get('DATA_NONPROD_SCHEDULES_ENABLED') != 'true':
            raise ValueError('Only explicitly enabled nonproduction schedules are supported')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_/-]{0,99}', values.get('DATA_NOTIFICATION_OWNER', '')):
            raise ValueError('Assign a notification and freshness review owner before schedule opt-in')
    elif event == 'workflow_dispatch':
        if (values['GITHUB_REF'] != f'refs/heads/{branch}' or values['GITHUB_SHA'] != sha
                or values['DATA_REQUESTED_TARGET'] != target):
            raise ValueError('Dispatch must select the promoted branch, approved SHA and explicit target')
    else:
        raise ValueError('Unsupported workflow event')
    return sha


def api(path, *args):
    return subprocess.check_output(['gh', 'api', path, *args], text=True)


def main():
    try:
        repo = os.environ['GITHUB_REPOSITORY']
        branches = api(f'repos/{repo}/branches?per_page=100', '--paginate', '--jq', '.[].name').splitlines()
        environment = os.environ['DATA_ENVIRONMENT']
        branch = 'Prod' if environment == 'prod' else latest_release_branch(branches)
        branch_sha = json.loads(api(f'repos/{repo}/git/ref/heads/{branch}'))['object']['sha']
        sha = approve(os.environ, branches, branch_sha)
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
            output.write(f'sha={sha}\n')
    except Exception:
        # Do not echo API payloads, inputs, tokens, or target details.
        print('Data workflow guard failed. Check approved SHA, promoted branch, Environment and target configuration.')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

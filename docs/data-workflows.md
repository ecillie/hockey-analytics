# Data update, dataset build, and manual refill workflows (Phase 7)

Phase 7 supplies 13 independent `data-update-*.yml` workflows,
`data-dataset-build.yml`, and **`database-refill.yml` with `workflow_dispatch`
as its only trigger**. The workflows call `.github/actions/data-job`, which runs
`app.jobs.workflow`. That adapter invokes the existing named job `run` entrypoints
or `app.database_setup.run_setup.run_setup`; source processing remains in the
existing Python operations. No workflow dispatches another workflow.

**Production scheduling is disabled in code.** Scheduled jobs always select
`nonprod`; the guard rejects scheduled production execution even if a variable is
misconfigured. Nonproduction scheduling is also off unless the repository variable
`DATA_NONPROD_SCHEDULES_ENABLED` is exactly `true`. Leave it unset/false during
Phase 7. Production recurring writes require a reviewed Phase 11 change.
No resources, secrets, database bindings, migrations, or live connections are
created by these definitions. Existing migration/promotion workflows remain separate.

## Code selection and credentials

GitHub schedules execute workflow definitions from the default branch. Keep the
reviewed workflow definitions and bootstrap guard there through normal promotion;
install the same changes on the promoted release branch before manual dispatch.
See [GitHub's schedule semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Each data job declares its `nonprod` or `prod` GitHub Environment. Before any step
receives a database credential, the guard verifies the following:

- `DATA_TARGET_ID` is a prepared database UUID.
- `DATA_APPROVED_SHA` is an immutable 40-character commit SHA equal to the current
  promoted branch head: newest numeric `Release-MAJOR.MINOR.PATCH` for nonprod,
  `Prod` for prod. Promotion does not update this variable automatically. New code
  cannot run until an operator updates the Environment's approved SHA after review.
- Manual dispatch selects that exact branch/SHA and supplies the matching target
  UUID explicitly. A tag, feature branch, old release, stale SHA, or wrong target fails.
- A schedule targets nonprod and has the repository opt-in enabled.

The next checkout uses the verified SHA with persisted Git credentials disabled.
Only the execution step receives the Environment-scoped `DATABASE_URL`. The
runtime checks the database's actual environment binding and UUID again before
any job writes. It never initializes/binds/migrates a database or bootstraps IDs.
Prepare those separately following [local persistence](local-persistence-datasets.md).
Use direct PostgreSQL connections with session affinity; transaction pooling is
incompatible with the session-fenced writer reservations.

Configure both GitHub Environments before live integration. Restrict prod to
`Prod`; restrict nonprod to the selected release branch and, only when enabling
nonprod schedules, the protected default branch. Protect those branches and
require Environment reviewers as appropriate. Environment restrictions are the
platform boundary preventing modified feature-branch workflow code from obtaining
secrets; an in-repository guard cannot protect against its own malicious rewrite.
Live restrictions and runner-to-database connectivity remain Phase 8–10 checks.
Workflow token permissions are `contents: read`; no cloud credentials or OIDC token
are requested in Phase 7.

| Setting | Location | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | Separate nonprod/prod Environment **secret** | Direct connection to that prepared database |
| `DATA_TARGET_ID` | Each Environment variable | Existing `pipeline_target.target_id`; never a URL or password |
| `DATA_APPROVED_SHA` | Each Environment variable | Reviewed promoted branch head; update explicitly after promotion |
| `DATA_NONPROD_SCHEDULES_ENABLED` | Repository variable | Default false; opt in only after nonprod live verification |
| `DATA_NOTIFICATION_OWNER` | Repository variable | Assigned GitHub login/team responsible for failure notifications and freshness review; required before schedule opt-in |
| `DATA_RUNNER` | Repository variable | Default `ubuntu-latest`; use a dedicated Linux self-hosted runner label for retained mounts/private networking |
| `DATA_<JOB>_ENABLED` | Environment variable | Optional `true`/`false`; blank uses reviewed job default |
| `DATA_<JOB>_LOOKBACK_DAYS` | Environment variable | Optional correction window override |
| `DATA_<JOB>_MAX_INPUT_AGE_SECONDS` | Environment variable | Optional producer freshness override; `0` disables this additional gate |
| `DATA_<JOB>_MAX_BATCHES` | Environment variable | Optional partition batch bound; default 10000 |
| `DATA_DATASET_CONFIG` | Environment variable | Audited JSON path in approved checkout, when datasets are selected |
| `DATA_ARTIFACT_ROOT` | Environment variable | Absolute retained mounted artifact directory; no runner workspace/temp storage |
| `DATA_COVERAGE_CONFIG` | Environment variable | Independent population audit JSON path in approved checkout for final refill acceptance |

`<JOB>` is the uppercase Python job name, e.g. `GAME_DETAILS`,
`ROSTER_RECONCILIATION`, `MONEYPUCK_SHOTS`. Refill also accepts
`DATA_REFILL_ENABLED` and `DATA_REFILL_MAX_BATCHES`; individual refresh disabled
states do not silently remove producers from a full refill.

## Independent schedules and scope

`.github/data-jobs.json` holds each job's enabled state, UTC cron, correction
window, and freshness threshold. Change it and run
`python3 .github/scripts/generate_data_workflows.py`; CI rejects generated drift.
Each workflow retains its own trigger, concurrency group, manual dispatch, and
producer controls. Cron expressions are reviewed code, not interpolated variables.
They are staggered off the hour; timestamps below are UTC and do not follow DST.

| Job | Cron | Lookback days | Max producer age seconds |
| --- | --- | ---: | ---: |
| teams_seasons | `17 6 * * *` | 7 | 0 |
| player_profiles | `27 6 * * *` | 7 | 0 |
| team_rosters | `37 */6 * * *` | 7 | 172800 |
| source_id_mappings | `47 */6 * * *` | 7 | 172800 |
| contracts | `7 */6 * * *` | 7 | 172800 |
| basic_stats | `17 */6 * * *` | 7 | 172800 |
| transactions | `23 */3 * * *` | 3 | 172800 |
| roster_reconciliation | `43 */3 * * *` | 3 | 172800 |
| game_schedule | `13 */3 * * *` | 7 | 172800 |
| game_details | `33 */3 * * *` | 7 | 172800 |
| moneypuck_stats | `19 10 * * *` | 7 | 172800 |
| moneypuck_shots | `39 10 * * *` | 7 | 172800 |
| edge | `59 */6 * * *` | 2 | 172800 |
| datasets | `49 12 * * *` | 0 | 172800 |

Refresh defaults select the source-resolved current season and game types `2,3`.
An explicit current start year can be supplied for deterministic reruns. Blank
current season resolves from NHL `standings/now`, verifies one coherent season,
and fails closed if unavailable; there is no calendar-year guess. Standalone
datasets use regular season only and their audited configuration's first/last
years. Other manual dispatches can explicitly bound the first/last year. Current-only
transactions/roster reconciliation reject historical ranges; transaction lookback
must be 1–31 days. No preseason, AHL, derived shot summaries, training, or prediction
workflow is introduced.

Accepted signing/extension refresh requests are coalesced and acknowledged by the
existing contract collector on its next independent run. Failed/validation-only
collections leave them pending. Profile/mapping discovery and roster reconciliation
likewise use their existing accepted inputs on their next run; no Actions dispatch
chain is necessary. Producer freshness failures defer only that job.

## Manual refill and bounded continuation

Dispatch `database-refill.yml` from the approved promoted branch. Supply
`environment` and `target_id`. Inputs default to `validation_only=true`, the
source-resolved current season, history starting at 2008, and eight new job/season
partitions per dispatch. Set `validation_only=false` explicitly to populate the
prepared target. `jobs` blank includes every source producer and includes datasets
when `DATA_DATASET_CONFIG` is configured. Explicit selections are targeted loads.

The existing setup planner orders producers before consumers and current season
before eligible history within each producer. NHL, MoneyPuck, and contracts begin
in 2008; EDGE begins in 2021. Transactions and roster reconciliation use only the
current season. Source selection, provenance, identity checks, coverage policy,
and transaction atomicity are unchanged. Schema changes/reset/deletion are never
part of refill.

A single process holds the **union of all requested database write/read
reservations**, including not-yet-executed partitions, across the dispatched run
and its final coverage check. Every refresh honors these database locks, even
across workflow files and separate processes. GitHub concurrency adds per-job /
per-environment serialization with `cancel-in-progress: false`; it does not replace
database reservations and is not a durable queue.

After eight new partitions (configurable `max_partitions` 1–1000), the process
reports incomplete and exits nonzero. **Continue with another manual dispatch**:
same target, approved implementation, current season, first/last range, selected
jobs, dataset cutoff/definitions, `validation_only=false`, and `resume=true`.
Completed durable partitions are checked without consuming the new-partition
quota, so each continuation progresses. Changes to scope/checkpoint semantics or
source enumeration must be reviewed before resuming. Never use a fresh source
season automatically for a continuation: explicitly pin the original year.

The shared action requires GNU `timeout` (included on the default Ubuntu runner)
and sends SIGINT after 300 minutes and SIGKILL after another minute
if necessary; the job timeout is 330 minutes including dependency installation.
Python normally records cancellation and releases its reservation on SIGINT.
Hard runner/job termination may prevent a final report; the last committed
database checkpoint remains authoritative. A session disconnect releases its
locks and fences the old writer. Each new manual dispatch reacquires the entire
reservation; no lock is promised during the gap between separate dispatches.
Refreshes during that gap still use CAS/validated writes; final audits run against
the reserved accepted view. No continuation auto-dispatches or cancels an active
refill. No runner workspace or Actions cache stores authoritative progress.

## Final coverage and dataset acceptance

Successful collectors alone cannot establish complete refill coverage. The final
check calls `validate_setup` against every requested policy partition while still
holding the refill reservation. An independent audit must specify the exact
canonical key population; expected counts are never inferred from loaded rows.

`DATA_COVERAGE_CONFIG` names a reviewed JSON file in the approved checkout:

```json
{
  "target_id": "<prepared target UUID>",
  "audit_reference": "<independent source population audit and date>",
  "scope": {"current_season": 2026, "first_season": 2008, "last_season": 2026, "game_types": [2, 3]},
  "partitions": [
    {"dataset": "teams", "expected_keys": [[10], [20]]},
    {"dataset": "basic_stats", "season": 2008, "game_type": 2, "expected_keys": []}
  ]
}
```

This illustrates structure only, **not a usable coverage claim**. Supply every
required partition with independently verified canonical keys from the logical
record key definitions. Empty keys certify zero expected records only if the audit
independently proves that population is empty. Missing, extra, duplicate, out-of-scope,
or mismatched-target evidence cannot pass. For large populations such as shots, use `expected_count` and
`expected_key_digest` instead of `expected_keys`: derive both from the independent
canonical key population. The digest is SHA-256 over the unique canonical JSON key
arrays sorted by UTF-8 bytes, each followed by a newline (empty population hashes
empty bytes). This keeps the approved audit compact without inferring population
from database rows. Both cardinality and digest must match.

Game statistics/events resolve season and game type through accepted game references. Optional EDGE partitions may be
absent and remain reported. Counts/issue codes go into sanitized reports; detailed
identities stay in the audit/database. No source data is fabricated to close gaps.
Absent audit evidence permits population work but final acceptance remains failed.
Live source audits remain Phase 9 work.

`full_refill_complete=true` requires the full 2008-to-current source scope, every
requested partition processed, a passing coverage gate, and write mode. Selected
jobs/ranges report `kind=selected_backfill`; validation-only can never claim a
completed full refill. Dataset manifests are also checked if datasets were selected.

The dataset JSON retains Phase 6's explicit cutoff, audited definitions, and exact
eligible player-season populations, adding `first_season` and `last_season` for
independent workflow scope. Refill uses that selected dataset range after source
producers finish. The artifact root is supplied separately and cannot be a path
inside the runner workspace/temp tree. Write publication requires a retained mounted
filesystem (e.g. a dedicated self-hosted runner's persistent volume); ordinary hosted
runner disk is rejected. Configure/persist/back up that volume before enabling live
dataset writes. Cloud artifact adapters and real retention/access/recovery acceptance
remain Phases 9–10. Uploading an Actions report is not durable dataset storage.

## Failure and recovery runbook

| Result | Next action |
| --- | --- |
| `0`, complete | Review scope and coverage; selected backfill is not full refill |
| `1`, partial/budget/final coverage failed | Inspect job statuses and coverage codes; manually continue the same refill with resume, or repair the independent audit/source gaps |
| `2`, invalid configuration | Correct target/Environment/ref/input/audited config or retained artifact mount; no automatic fallback target |
| `3`, prerequisites/freshness/writer conflict | Check required producer runs or active refill; rerun affected producer/job independently after the cause clears |
| `4`, disabled | Restore that job's reviewed enabled state if execution is intended |
| `130`, cancelled | Inspect durable run/checkpoint and manually resume refill; refreshes rerun their correction window |
| Shell `124`, timeout, missing report, or runner loss | Treat as incomplete; inspect durable database state, ensure the old session is gone, then manually resume |

A source enumeration digest change makes offset resume unsafe. The existing
collector refuses it. Manually rerun that affected job/season without resume using
a targeted refill selection, then manually resume the original scope. Duplicate
reruns are idempotent; do not edit checkpoints or bypass validation. Lost commit
responses are resolved through retained exact batch receipts. Never delete those
receipts, retained input revisions, or published artifacts.

After a missed/delayed schedule, inspect last successful committed producer runs
and pending refresh requests. Manually rerun only affected refreshes with a
reviewed correction lookback covering the missed interval. For transactions the
31-day source bound still applies; older missing history cannot be invented.
Use the manual refill workflow with explicit jobs/ranges for older supported
backfills. Rebuild selected datasets only after their inputs/audits pass. GitHub can
delay/drop scheduled runs or replace a pending concurrency run, so scheduled events
are not evidence of freshness. Staleness remains measured from committed runs.

Assign `DATA_NOTIFICATION_OWNER` to the GitHub login/team operating data workflows.
The schedule guard requires this assignment before opt-in. That owner handles
failed-run notifications and daily freshness review; enable GitHub Actions failure
notifications for the assigned owner before live opt-in. Reports do not email or message anyone. In Phase 10,
verify actionable missed-run/staleness monitoring and name the launch owner in the
operations runbook. A passive Actions failure alone cannot detect a job that never
started.

Only `coverage/data-workflow/report.json` is uploaded, retained for 14 days. It
contains allowlisted statuses/counters, safe issue/coverage codes, and no raw rows,
URLs, secrets, full exceptions, or checkpoint tokens. Structured diagnostics go to
stderr; database records retain detailed progress. The step summary includes
completion/exit status and per-job accepted/rejected/unresolved counts. Artifacts
and runner logs are diagnostics, not resume state or dataset retention.

With scheduling disabled, new scheduled execution minutes are zero. Enabling all
nonprod crons requests 57 runs/day (1710 in a 30-day month): at an assumed five
minutes/run, about 8550 runner minutes plus manual refills and CI; at 20 minutes,
34200. These are planning estimates, not measured throughput or billing. The
300-minute execution bound is a ceiling, not a cost estimate. Verify plan allowance,
runner charges, disk capacity, retention costs, and realistic durations before
nonprod opt-in; measure production scale in Phases 9–10.

## Local and CI validation

```bash
python3 -m pip install -r backend/requirements-dev.txt
python3 .github/scripts/validate_data_workflows.py
actionlint -shellcheck='' .github/workflows/data-*.yml .github/workflows/database-refill.yml
PYTHONPATH=backend python3 -m pytest --no-cov -q backend/tests/test_data_workflows.py
```

For database checks, use a **disposable PostgreSQL database only**. Apply the
existing migrations and set `TEST_DATABASE_URL` to its direct URL before running:

```bash
PYTHONPATH=backend python3 -m pytest --no-cov -q \
  backend/tests/test_data_workflow_persistence.py \
  backend/tests/test_pipeline_persistence.py \
  backend/tests/test_execution_foundation.py \
  backend/tests/test_phase6_job_controls.py
```

The persistence tests truncate test ledger tables. They test fresh-adapter manual
continuation, cancellation/resume, final-gate reservations across independent
sessions, and existing session-loss/receipt recovery guarantees. Offline checks
also reject automatic refill triggers/callers, wrong refs/targets, production
schedule attempts, unsafe scopes, false completion, and transient dataset storage.
The shared CI runs policy/generation checks, actionlint 1.7.7, and the configured
backend/ML suite with its disposable PostgreSQL service. Live Actions dispatch,
Environment protection/secret behavior, managed database networking, scale, and
AWS/durable artifact recovery remain Phases 9–10 gates.

Local verification on 2026-10-16: **731 tests passed with no skips**, 85.39%
branch-aware backend/ML coverage, 100% API service coverage, and a passing committed
OpenAPI check. All 15 workflow definitions pass generation/policy checks and
actionlint 1.7.7. A separate real-runtime rehearsal on a fresh nonprod-bound
disposable PostgreSQL 15 database completes three manual continuations, the final
independently declared population audit, and an independent refresh with offline
source fixtures. Changed Python modules compile on Python 3.12; runtime tests used
Python 3.11. No live GitHub dispatch or AWS connection was made.

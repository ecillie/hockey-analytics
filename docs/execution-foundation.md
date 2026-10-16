# Replacement pipeline execution foundation (Phase 2)

Phase 2 implements explicit setup/job entrypoints and a shared execution path
against the Phase 1 logical records and injectable access contracts. It is
verified offline with reference records and a dependent membership load. Core
source adapters are implemented in [Phase 3](core-data-pipelines.md); game,
MoneyPuck, and EDGE adapters are implemented in [Phase 4](game-tracking-pipelines.md).
[Phase 6 infrastructure](local-persistence-datasets.md) implements local PostgreSQL
connections, durable run/checkpoint state, and session-fenced reservations.
AWS/production integration is verified in Phase 9. No recurring schedules are activated.

## Runtime boundary

Infrastructure supplies an `Executor` bound to an actual target environment,
a conforming `DataStore`, registered `JobOperation` instances, and optionally a
`SourceClient`. Setup never creates connections, schemas, or migrations. An
unregistered operation reports `deferred` and exits unsuccessfully; an empty
module or empty iterator cannot pass as a source load.

Each job has its own module, for example `app.jobs.teams_seasons`. Setup uses
`app.database_setup.run_setup`; selected historical runs use
`app.database_setup.backfill`. Individual `load_*` modules select their shared
job operations. Imports do not collect, connect, execute, or register schedules.

CLI runtimes are explicit `module:factory` references. The factory receives the
requested environment and returns an `Executor`; infrastructure must verify
its credentials/connection against that environment. Matching labels alone do
not prove production isolation. No production runtime is supplied in Phase 2.
The current/latest season must be resolved by the calling runtime/source before
execution, then supplied as its start year. There is no hard-coded latest season.

## Offline demonstration

Run from the repository root with the development dependencies installed:

```bash
PYTHONPATH=backend python3 -m app.database_setup.run_setup \
  --environment dev --current-season 2026 --first-season 2026 \
  --jobs teams_seasons player_profiles team_rosters \
  --runtime tests.execution_fixtures:create_runtime --validation-only

PYTHONPATH=backend python3 -m app.jobs.teams_seasons \
  --environment dev --current-season 2026 --mode refresh \
  --runtime tests.execution_fixtures:create_runtime

PYTHONPATH=backend python3 -m pytest \
  backend/tests/test_execution_foundation.py \
  backend/tests/test_source_requests.py backend/tests/test_normalization.py --no-cov
```

Setup JSON includes a `runs` array of detailed reports with the same `run`,
`issues`, `error`, counts, and cursor fields as independent-job JSON.

These commands print JSON reports and use a test-only in-memory store. Each CLI
invocation creates a fresh fixture store; it cannot demonstrate cross-process
resume or a database connection. The tests use the same injected store across
invocations to demonstrate reruns, corrections, failed-batch resume, and lost
commit responses. The fixture runtime accepts `dev` only and performs no network
requests. Its fixture year is a test input, not a source availability claim.

## Collection and acceptance

`JobConfig` requires a job, environment, adapter target environment, mode, current
season, and requested season range. It supports explicit enable/disable, resume,
correction lookback, and batch limits. MoneyPuck/NHL/contracts start at 2008;
EDGE starts at 2021. Only distinct regular-season/playoff game types (`2`, `3`)
are accepted. Transactions and current roster reconciliation cannot be backfilled.
Resume is restricted to initial loads and backfills. Refreshes recollect their
correction scope; validation-only execution always validates its declared scope.

A `JobOperation` supplies a collector and optional source normalizer. Dependent
jobs also require a readiness function returning exactly `True`; it must verify
the actual requested references, coverage, and freshness. Row presence alone is
insufficient. Source adapters own scope discovery, filtering preseason records,
source precedence, correction windows, and independent enumeration evidence.
Setup sorts selected jobs by their dataset dependencies and completes each
producer’s requested partitions before starting consumers. It loads the current
season first within each job, then eligible history. This establishes older season
references before a current multi-season contract or downstream dataset needs
them. Dependencies outside the selection must already be verified ready; setup
does not silently add unrequested jobs.

Collectors yield bounded `CollectionBatch` objects with normalized candidates,
source observations, an advancing JSON cursor, an independently established
expected batch count, a collection-completion flag, and an explicit final flag.
A verified empty population is represented by an empty final batch with expected
count zero. Unknown counts, incomplete batches, malformed records, duplicate keys,
broken relationships, and unresolved identities block the whole batch. The run
retains review issues and valid raw observations but does not advance its checkpoint.

All optional transforms share whitespace/missing-value handling. Required fields
are still enforced by the typed record validator. Common helpers normalize explicit types, dates, aware UTC timestamps, exact USD
cents, and durations. Missing values stay missing; money is never rounded and
names never establish identity. Source IDs resolve through validated mappings
and existing canonical records. Initial, backfill, refresh, and validation modes
use the same typed, scope, unique-key, and relationship checks.

## Commit and recovery

The executor reserves output datasets exclusively and dependency datasets for
shared reads through `DataStore.writer_lease`. Jobs producing different outputs
may read the same references concurrently. Reference writers exclude active
readers. Setup reserves the union of selected output datasets before beginning
and retains those reservations across every selected partition; external
prerequisites retain shared read reservations. Overlapping writers defer and
separate environments remain isolated. Transactions still protect the relevant
accepted record/reference scopes for their atomic batch commit.

The Phase 6 PostgreSQL adapter makes every adapter writer honor these reservations
and fences execution on session loss. AWS session/failover behavior remains a
Phase 9 gate. The in-memory test lease establishes interface behavior only.

Each accepted batch atomically commits changed records, raw observations, run
counters, an idempotency receipt, and checkpoint progress. Upload retries reuse
one immutable batch ID/content, including after a lost commit response. Revision
and idempotency conflicts are never blindly retried. Corrections create revisions;
identical records retain their accepted revision while new observations remain
traceable. Append-only identities cannot be corrected.

Checkpoints are independent per environment/job/hashed mode-and-range scope.
Their cursor envelope is `{"version": 1, "position": ..., "complete": bool}`.
Cursor envelopes are strictly validated and repeated cursors cannot rewind a run.
Only committed contiguous progress advances. `--resume` continues an incomplete
initial/backfill scope or skips a previously completed scope. Omit `--resume` to
recollect a selected scope for corrections. Neither action resets other jobs.

Run reports distinguish success, no change, partial progress, failure, deferred
inputs/conflicts, disabled jobs, and cancellation. Read counts include a failed
upload's candidates; accepted counters describe committed or validation-only
accepted records. Control revisions are excluded from `written`/`unchanged`.
If terminal reporting itself fails, the returned report exposes that failure;
committed records, running counters, and checkpoints remain recoverable.

Validation-only execution makes no writes, receipts, checkpoints, or writer
reservations. A temporary record overlay lets later setup jobs validate against
accepted earlier candidates, using one consistent base snapshot across the entire
validation-only setup. It is discarded after the invocation and cannot
establish database integration or production concurrency behavior.

## Requests and completion evidence

`SourceClient` requires a per-source `RequestPolicy`: finite timeout, minimum
request interval, retry count, request budget, response-byte limit, and bounded
retry delay. It retries transient transport errors and selected transient HTTP
statuses. Permanent failures and malformed JSON fail explicitly. Requests use
HTTPS and do not follow redirects outside rate accounting. Long `Retry-After`
values defer collection and block subsequent requests until the source deadline;
they are never shortened into an earlier retry. A source wait cannot block
requests to a different source, and Retry-After remains effective even when the
last allowed request attempt fails. Source and upload retries share bounded
backoff timing. Transport, clock, and sleep are
injectable for repeatable fixtures. The request budget applies to the supplied
client's lifetime; infrastructure chooses its run lifetime.

`SetupReport.complete` means the requested operations completed, not that the
whole release's sources are populated. `setup_partitions` enumerates baseline
partitions from declared work. `validate_setup` requires every selected partition
and independent coverage observations; missing required evidence blocks the gate.
Counts cannot replace adapter checks of exact populations and optional fields.
Final full-database checks, source availability evidence, and release completion
remain later gates.

## ETL responsibilities

The collector extracts source pages and retains raw observations. The source
normalizer maps source fields and units; shared validation enforces the logical
contracts, scope, identities, and relationships. Write preparation deduplicates
unchanged records and seals corrections before the upload boundary commits data,
lineage, counts, and checkpoint together. The executor coordinates those stages;
run tracking owns counters, terminal reports, and cursor serialization.

Holding an entire invalid batch is intentional for this foundation: a bad or
unresolved reference cannot leave an accepted fact or advance progress past a
coverage gap. Review issues retain the reason, and reruns use the normal acceptance
path after resolution. Production adapters must additionally establish transaction
isolation, durable idempotency receipts, and crash recovery; source adapters must
establish complete enumeration and source-specific acceptance rules.

## Shared rules and defaults

Job, setup, and backfill entrypoints use the same CLI option/default builder and
execution-mode policy. The original request is checked before applying
validation-only mode, so it cannot bypass the transaction backfill restriction.
Run counters also use one validated update path for both immediate read counts
and accepted-count previews that become durable with a batch commit.

The small job and population modules remain explicit delegates to shared
operations. Source parsing and acceptance logic belong to the reusable operations;
adding a source adapter should not add a separate setup implementation. Validation
at record and persistence boundaries remains necessary even when entrypoint
configuration has already been checked.

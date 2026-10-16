# Local persistence, consumers, and datasets (Phase 6)

PostgreSQL remains the selected engine. Migration `20261015_0003` adds a
replacement revision ledger beside the existing tables. No AWS resource,
production connection, schedule, training job, or inference service is created.

## Storage and transition

`database.pipeline.store.PostgresStore` implements the existing injectable access
contracts. Infrastructure, schema changes, connection selection, environment
binding, locks, and local artifact storage live under `backend/database/pipeline/`.
Source jobs and setup receive the adapter through an explicit runtime factory.

Each physical database has one explicitly initialized `pipeline_target` binding:
environment, target UUID, and snapshot signing secret. The adapter verifies the
actual binding rather than trusting a supplied environment label. A prod-labelled
runtime cannot use a dev-bound database. Initialization cannot retarget a bound
database. Database access privileges, separate users, and clone/recovery identity
rotation must also be verified during AWS integration.

`pipeline_records` retains every accepted canonical record revision and its
sealed write envelope, payload, digest, provenance UUIDs, acceptance time, and
committing run. `pipeline_receipts` retains exact batch retry receipts. Runs,
review issues, source observations, refresh requests/completions, and checkpoints
use the same atomic ledger. There is no deletion/expiration API. Published input
revisions and artifacts have indefinite retention in this local implementation.

Apply migrations and bind a **local/disposable** target explicitly:

```bash
export ENV=dev
export DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/DISPOSABLE_DATABASE
export DEV_DATABASE_URL="$DATABASE_URL"
python3 -m alembic -c backend/alembic.ini upgrade head
PYTHONPATH=backend python3 -m database.pipeline.runtime --environment dev
```

When existing `public.players`/`public.teams` identities are present, transition
their canonical IDs before collecting replacement data:

```bash
PYTHONPATH=backend python3 -m database.pipeline.runtime \
  --environment dev --bootstrap-identities
```

This additive operation copies identities and explicit NHL mappings with retained
bootstrap evidence. It preserves the existing public IDs and newer accepted
profile attributes on reruns. It does not copy performance/contracts, infer name
matches, or delete legacy records. Run the transition with legacy identity
writes quiesced. The source runtime refuses to start until every legacy identity
has its corresponding canonical mapping. New source-ID collisions remain held
for review rather than renumbering or overwriting an existing entity.

## Transactions, reservations, and recovery

Commits validate canonical envelopes, source-identity uniqueness, references,
contract/game relationships, provenance, manifest revision pins, record CAS, and
checkpoint CAS against the locked accepted view. Records, run counters, review
issues, progress, and the receipt commit together. Stale revisions and checkpoints
roll back the entire batch; exact retries return the original durable receipt.
Reusing an ID with different content fails. Uncommitted contexts write nothing.

A dedicated database session holds ordered PostgreSQL advisory locks for the
entire job/setup: exclusive output reservations and shared dependency reservations.
Every adapter transaction honors those reservations and checks actual output
dataset scopes. Setup retains the union across all selected jobs, excluding
refreshes between batches and producers. Unrelated reservations may coexist.

A short transaction advisory lock serializes commits, making reference validation,
uniqueness, CAS, and snapshot high-water marks consistent. This favors correctness
for the initial implementation; production-scale throughput remains a Phase 9
measurement. Lock keys are stable across processes. Connections must support
session affinity; transaction-pooling proxies are unsupported for writer leases.

The database session is the lease and its fence. A crash/disconnect releases its
reservations. An active reservation never reconnects after losing that session;
further commits fail and require a fresh run/resume. If a commit response was lost,
retry the identical batch on a fresh adapter to recover its receipt, then resume
from committed progress. No runner workspace checkpoint is authoritative.

Snapshots carry a signed, target/environment/cutoff-bound commit watermark. Reads
and keyset cursors preserve that accepted view across corrections and pages.
Filters apply to the selected revision, so an old matching revision cannot
reappear after its current value changes. Exact retained revisions remain readable.

## Existing consumers

Migration-owned `pipeline_api` views map accepted records into the existing table
and column shapes. The service and public response schemas remain unchanged.
`DATA_QUERY_SCHEMA=public` stays the default. Explicitly select
`DATA_QUERY_SCHEMA=pipeline_api` for a populated replacement target; new physical
consumer connections also verify its environment binding.
The selected schema has no public-table fallback: a missing replacement view
fails the request instead of silently switching the data source.

The projections preserve nullable values, cents, ratio decimals, current-team
ordering, server-side sorting/pagination, and TOTAL-before-TEAM aggregation.
NHL basic statistics take precedence over Cap Space, at the whole
player/season/game-type/stat-kind grain; one provider's TOTAL cannot combine
with another provider's stints. MoneyPuck supplies advanced statistics.
Existing model versions and predictions remain readable from public tables;
accepted replacements supersede matching model/prediction IDs. No model is trained
or activated by this phase. Collection history still begins at 2008.

ML uses these same projections. Its existing stint query now preserves null
measurements instead of turning an entirely unavailable measure into zero.
The full populated fixture compares identities, skater/goalie stats, values,
contracts, team cap/rosters, search, leaders, overview, comparison, sorted/filtered
pages, and both ML queries across the old and replacement storage paths.

## Job controls and event requests

Each standalone job accepts `--game-types`, `--correction-lookback-days`,
`--max-input-age-seconds`, `--max-batches`, `--max-batch-records`, `--disabled`,
validation-only, and applicable resume options. Age zero disables the additional
freshness gate. A positive value requires successful committed producer runs,
covering every requested season/game type, within that age. Validation runs and
future-dated success records cannot establish freshness. Source-specific readiness
checks still apply. [Phase 7 workflows](data-workflows.md) supply independent job defaults, guarded
manual dispatch, bounded refill continuation, and final audited coverage checks.
Production schedules remain disabled.

Accepted signing/extension requests coalesce by player in the contract collector.
A successful collection commits immutable `refresh_completions` for each exact
cause; failed collection leaves them pending, and validation-only writes no
acknowledgements. New transaction corrections create new requests. A completion
links its refresh run and original request under logical contract version 3.

CLI JSON remains on stdout and sanitized structured diagnostics on stderr.
Exit codes are `0` complete, `1` failed/partial, `2` invalid configuration,
`3` deferred prerequisites/conflict, `4` disabled, and `130` cancelled.
Incomplete or deferred work never receives a success exit code.
Deferred reports include safe `reason_code` values for unconfigured operations,
unready inputs, stale inputs, and writer conflicts. Freshness thresholds are
included in scoped reports and structured diagnostics.

## Dataset definitions and publication

`app.jobs.dataset_processing` builds independently defined skater or goalie
datasets. The grain is one eligible **regular-season player-season**. Playoff
source data stays available but is excluded from these model dataset definitions.
Contracts never enter performance features or targets. The dataset job runs once
over its requested season range after source producers finish.

Every definition supplies a unique dataset ID, kind, minimum games (default 20),
train-through target season, validation target season, test target season, and an
**independently audited exact eligible player-season population** plus its audit
reference. The population must include target-input seasons. It cannot be inferred
from the rows that happened to load. Missing/extra identities and duplicate totals
or stints block publication. No coverage percentage waiver is provided.

| Input/output | Rule |
| --- | --- |
| Basic stats | NHL before Cap Space, then TOTAL before distinct TEAM stints; minimum games eligibility |
| Advanced stats | MoneyPuck `all`, same player/season/game type; TOTAL before stints |
| Identity/cap | Exactly one profile and season join; known position and salary-cap cents required |
| Skater performance | Game Score per 60; positive TOI and non-null Game Score required |
| Goalie performance | `(expected goals against - goals against) * 3600 / TOI seconds` |
| Replacement | Within season/position, median performance per 60 among the bottom 20% by TOI/game |
| Target | Following season's performance per 60 above replacement × following season's TOI hours |
| Splits | Assigned by **target season**; train ≤ train-through, then explicitly ordered validation/test years |
| Missing values | Incomplete required performance blocks publication; optional features remain null and their missingness is reported |
| Missing targets | Remain null, never zero; every supervised split needs observed eligible targets |
| Age | Full years on October 1 of the feature season |

Aggregations do not combine providers. An incomplete stint measure remains unknown.
Expected goals and other available raw performance measurements retain their source
units; TOI is seconds, salary cap is cents, percentages are ratios. The manifest
records definitions, exact key/revision/digest pins, scope, cutoff, eligibility,
quality results/missingness, row count, schema/transformation versions, and the
artifact digest. A definition change changes the artifact/version.

These are **retrospective accepted-snapshot datasets**. The cutoff excludes later
accepted corrections. It does not establish that a historical season's information
was available on an old prediction date. All published manifests explicitly set
`point_in_time_supported=false`; publication claiming historical point-in-time
support is blocked. There is no fabricated source-availability history.

Set `PIPELINE_DATASET_CONFIG` to a JSON file with `cutoff` (an explicit aware UTC
timestamp), `artifact_root` (local directory), and `definitions`. Each definition
contains `dataset_id`, `kind`, `train_through`, `validation_season`, `test_season`,
`min_games`, `coverage_audit`, and `expected_player_seasons` as `[player_id, year]`
pairs. Cutoff is fixed explicitly so reruns can reproduce a published version.
Without configured definitions, the datasets job defers.

```bash
export PIPELINE_DATASET_CONFIG=/absolute/path/to/audited-dataset-config.json
PYTHONPATH=backend python3 -m app.jobs.datasets \
  --environment dev --current-season 2026 --first-season 2020 --last-season 2024 \
  --game-types 2 --runtime database.pipeline.runtime:create_runtime
```

The builder validates the full result before storing canonical JSON bytes through
the injected artifact interface. Local storage fsyncs and atomically links a
SHA-256-addressed file without overwriting existing contents. Only then does the
executor publish the immutable manifest and checkpoint in PostgreSQL. A failed
database commit can leave an unreferenced artifact; exact retries reuse it safely.
Validation-only creates no artifact or manifest. Dry setup with unaccepted input
candidates defers dataset publication rather than inventing revision pins.

`reproduce_dataset(reader, environment, manifest, artifacts)` reads only the
retained pinned revisions and verifies rebuilt bytes and metadata against the
published artifact, including after later source corrections. Never delete a
referenced input revision or artifact. Cloud artifact storage/atomicity, access
control, backup/restore, and retention enforcement remain AWS acceptance work.

## Coverage policy and local verification

The local Phase 6 baseline accepts coverage policy version 3 unchanged: required
populations/fields have zero tolerated gaps, optional fields remain nullable, and
no historical contract or required EDGE exemption is granted. Contracts prefer
Cap Space with an explicitly verified CapWages fallback; partial conflicting
coverage remains held. NHL is the basic-statistics source. Transactions default
to three recent days, with a bounded configurable maximum of 31 days. AHL and
derived shot summaries stay excluded; EDGE games/events remain optional samples.

Run focused checks against a **disposable migrated** PostgreSQL database:

```bash
PYTHONPATH=backend TEST_DATABASE_URL=postgresql://USER@localhost/tradevalue_test \
  python3 -m pytest --no-cov \
  backend/tests/test_pipeline_persistence.py \
  backend/tests/test_dataset_processing.py \
  backend/tests/test_phase6_job_controls.py
```

Tests cover durable history, snapshot/cursor integrity, CAS rollback, uniqueness,
provenance, independent sessions, concurrent stale writers, refill reservations,
connection termination before receipt insertion, lost commit-response recovery,
setup/refresh/interruption/resume, preserved public IDs, consumer equivalence,
coalesced requests, freshness, quality blocking, and exact dataset reproduction.
Migration lifecycle tests verify empty initialization, repeat upgrade, offline SQL,
full downgrade/upgrade, and catalog/view drift snapshots.

Live upstream schema/availability audits, complete historical salary populations,
historical event limitations, EDGE availability, production-scale data volumes,
managed-service session/failover behavior, TLS/users/networking, cloud object
storage, and backup/restore remain Phases 9–10 evidence. Local source fixtures do
not certify live source coverage. A successful selected setup is still subject to
the independent requested-partition coverage gate in `validate_setup`.

Local verification on 2026-10-14: **686 tests passed with no skips**, 85.32%
branch-aware backend/ML coverage, and 100% API service coverage. The full run
includes migration round-trips/catalog checks and the committed OpenAPI check.
A fresh-database HTTP/real-CLI rehearsal publishes a dataset and verifies an
identical `no_change` rerun. Runtime tests used Python 3.11 and PostgreSQL 15;
changed modules also compile under Python 3.12.

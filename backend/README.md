# TradeValue backend API

The backend is a read-only FastAPI service backed by an Alembic-managed
PostgreSQL schema. It implements every route in `docs/api-contract.md`,
including player and team browsing, Hockey Value, contracts, cap estimates,
search, overview aggregates, and comparison.

## Local development

From the repository root:

```bash
python -m pip install -r backend/requirements-dev.txt
cp backend/.env.example backend/.env
python -m alembic -c backend/alembic.ini upgrade head
cd backend
uvicorn app.main:app --reload
```

If you use the individual `DB_*` variables instead of `DATABASE_URL`, apply the
schema with the equivalent connection arguments. The API is available at
`http://localhost:8000`; interactive OpenAPI documentation is at
`http://localhost:8000/docs`.

Health check:

```bash
curl http://localhost:8000/api/health
```

The health endpoint checks database connectivity. A database failure returns a
shared `DATABASE_UNAVAILABLE` error with HTTP 503.

The season catalog is intentionally historical/current only. A season becomes
available on July 1 of its start year, so 2026–27 is hidden through June 30,
2026 and becomes available on July 1, 2026. The same centralized cutoff powers
the current-season default, `/api/seasons`, and validation on every
season-scoped endpoint; inserting future contract seasons does not expose them
as selectable statistics seasons.

Hockey Value is calculated from the canonical all-situations advanced-stat row
using the repository's position/season replacement-level definition. A stored
next-season projection is returned only when a prediction payload explicitly
contains `predicted_hockey_value`; otherwise that field remains `null`.

## Frontend connection

Create `frontend/.env.local`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCK_API=false
```

Set `CORS_ORIGINS` in `backend/.env` to a comma-separated list of actual browser
origins. Do not use `*` when credentials are introduced later.

## Tests

```bash
PYTHONPATH=backend pytest -q backend/tests ml/tests
```

HTTP and service tests verify response contracts, validation errors, route
coverage, CORS, and service-layer branching. PostgreSQL integration tests run
when `TEST_DATABASE_URL` is set; the target database must be disposable because
the tests truncate application tables. CI provisions a dedicated PostgreSQL
service, migrates an empty database to Alembic head, verifies the catalog and a
downgrade/re-upgrade cycle, then runs the integration suite automatically.

The ingestion gate uses small checked-in MoneyPuck and CapWages-shaped fixtures;
it never calls live NHL, MoneyPuck, or CapWages services. It validates source
schemas and required values, season coverage, player/season/stat deduplication,
idempotent typed-field upserts, salary-cap reference data, foreign-key behavior,
and transaction rollback after a failed batch.

Every schema-native ingestion stage records `running`, `succeeded`, `failed`, or
`cancelled` state in `ingestion_runs`. PostgreSQL advisory locks reject a second
copy of the same stage while one is active. Successful rows are upserted and
source rows absent from a later snapshot are deliberately retained; loaders do
not infer deletion from absence. MoneyPuck coverage, volume, and duplicate-ratio
thresholds, NHL roster and schedule minimums, NHL stat invariants, and CapWages
profile-success thresholds fail before writes. An incomplete roster feed rolls
back the entire roster-status update.

The production defaults expect MoneyPuck seasons 2008 through 2025, at least 30
NHL teams, 500 active NHL players, 100 regular-season schedule games, and a 98%
CapWages profile success rate. Tests override only the volume values so tiny
fixtures exercise the identical validation and persistence paths.

To run the integration tests against a dedicated local test database:

```bash
createdb tradevalue_test
DATABASE_URL=postgresql://localhost/tradevalue_test \
  python -m alembic -c backend/alembic.ini upgrade head
TEST_DATABASE_URL=postgresql://localhost/tradevalue_test \
  PYTHONPATH=backend pytest -q backend/tests/test_postgres_integration.py
```

## Container

```bash
docker build -t tradevalue-api backend
docker run --rm -p 8000:8000 --env-file backend/.env tradevalue-api
```

Required CI builds this exact Dockerfile, starts the resulting image as a
non-root user against the disposable PostgreSQL service, waits for readiness,
and calls `/api/health`, `/api/seasons`, and `/api/teams` over the published
port. Container logs are printed automatically when the smoke check fails. The
request-serving image excludes ingestion code and its large local source data;
loaders run separately from a trusted environment.

The supported ingestion commands are documented in
`app/ScriptingFiles/FullDataScript/README.md`. CI compiles the complete backend
application and imports every supported ingestion module in a fresh interpreter
before running the database-backed suite. Obsolete ORM-based loaders are
retained under `legacy_loaders/` as non-executable recovery references; they are
not substitutes for PostgreSQL backups.

Production must provide `ENV=nonprod` or `ENV=prod`, a corresponding database
URL, and the deployed frontend origin in `CORS_ORIGINS`. Apply schema changes as
a separate release step; the API never mutates the schema on startup.

## Vercel + Neon deployment

Import this repository into Vercel twice. Configure the API project with Root
Directory `backend` and the web project with Root Directory `frontend`.
`vercel.json` in each directory pins the framework and routing behavior.

For the API project:

1. Add Neon from the Vercel Marketplace and connect it only to the API project,
   or add an existing Neon pooled connection string as `DATABASE_URL`.
2. Set `ENV=prod`.
3. Set `CORS_ORIGINS` to the exact production frontend origin, with no trailing
   slash, such as `https://tradevalue.example.com`.
4. Optionally set `CORS_ORIGIN_REGEX` to a project-specific full-match regex for
   preview URLs. Avoid a regex that permits every `vercel.app` deployment.
5. Deploy and confirm `/api/health` returns `{"status":"ok"}`.

Use Neon's pooled `-pooler` connection string for the running API. The app keeps
its local SQLAlchemy pool deliberately small so horizontally scaled Functions do
not create excessive client connections. Keep a direct, non-pooled Neon URL for
schema application and ingestion jobs; do not expose either URL to the frontend.

Apply migrations using the direct connection before the API deployment:

```bash
DATABASE_URL="$NEON_DIRECT_DATABASE_URL" \
  python -m alembic -c backend/alembic.ini upgrade head
```

The repository's manually dispatched `Database migration` workflow performs
this as a separately gated environment operation. Configure a direct,
non-pooled `DATABASE_URL` secret in both GitHub `nonprod` and `prod`
Environments, and require reviewers for the `prod` Environment.

For the frontend project, set these variables in both Production and Preview:

```dotenv
VITE_USE_MOCK_API=false
VITE_API_BASE_URL=https://your-api-project.vercel.app
```

Redeploy the frontend after changing either `VITE_` value because Vite embeds
them into the browser bundle at build time. The frontend's Vercel rewrite keeps
React Router URLs working when opened or refreshed directly.

The checked-in ingestion CSVs and scripts are excluded from the Vercel Function.
Run ingestion from a trusted machine or a separate job using
`requirements-dev.txt` and the direct Neon database URL.

## Replacement pipeline coverage policy

`app.jobs.shared.coverage` defines version 3 of the required/optional dataset
and field baseline for the replacement pipelines. It is independent of database
selection and has no network, upload, or scheduling side effects. Final scope
review is recorded in the local `planning/required-data-coverage.md` matrix.
The replacement scope excludes AHL collection, AHL roster evidence, and derived
shot-map/shooting summaries. Individual shots, MoneyPuck statistics, and NHL EDGE
season data remain in scope.

Use `check_record_coverage(dataset, record)` after source normalization to report
missing required and optional fields without changing the input. Missing values
stay missing; measured zeros are accepted. This is an availability check, not
the Phase 1 validation of types, units, identity, or source-specific rules.

Use `assess_coverage(requested, observations, current_season=..., mode=...)` to
check explicit dataset/season/game-type partitions. Each observation supplies an
independently established expected population, accepted counts, collection
completion, and validation/identity issues. A successful fetch or an unknown
expected count cannot establish complete required coverage. Independently check
exact identities, duplicates, and relationships before submitting evidence;
equal row counts alone cannot detect a missing player replaced by a duplicate.

```python
from app.jobs.shared.coverage import (
    CoverageObservation, CoveragePartition, assess_coverage,
)

partition = CoveragePartition("contract_seasons", season=2008)
evidence = CoverageObservation(
    partition=partition,
    expected_records=10,  # Historical participation audit, not loaded row count.
    accepted_records=8,
    collection_complete=True,
)
report = assess_coverage([partition], [evidence], current_season=2026)
assert not report.complete
assert report.issues[0].code == "MISSING_RECORDS"
```

Required gaps block completion; optional gaps remain in `report.issues` without
blocking. `report.complete` describes only the explicitly requested scope,
not the whole release. It does not permit uploading invalid optional records.
Callers must enumerate the entire required scope for a setup/release gate and
derive transaction date windows, season upper bounds, and expected populations
from validated source/reference evidence. Live source jobs are not implemented
yet. The Phase 2 setup gate enumerates selected partitions and requires explicit coverage evidence; a coverage result
alone never authorizes checkpoint advancement or upload.

Run the offline policy tests with:

```bash
PYTHONPATH=backend python -m pytest backend/tests/test_data_coverage.py --no-cov
```

# Replacement data contracts (Phase 1)

`app.jobs.shared.data_contracts` defines 32 logical record families, their keys,
units, relationships, and correction/history requirements. Every coverage output
has a contract. Validate normalized Python records or JSON without a database:

```python
from app.jobs.shared.data_contracts import validate_record

record = validate_record("contract_seasons", {
    "contract_id": 1, "player_id": 7, "season": 2025,
    "cap_hit": 800_000_000, "is_slide": False,
})
```

`app.jobs.shared.access_contracts` supplies injectable reader, transaction, and
checkpoint interfaces plus immutable normalized write envelopes. Adapters must
preserve revisions, atomically commit records/provenance/progress, reject stale
revisions, isolate environments, and recover exact batch retries. The in-memory
adapter lives in the test package; real adapters and query integration are
Phase 6 local work, followed by Phase 9 AWS verification.

`app.jobs.shared.consumer_contracts` defines all existing API query projections,
maps all 18 endpoints, and defines the ML player-season/salary-cap reader shapes.
Existing consumers and public contracts remain unchanged. The dictionary,
relationship diagram, access requirements, compatibility checklist, and exported
JSON schema are local planning artifacts under the ignored `planning/` directory.

Run the offline contract checks with:

```bash
PYTHONPATH=backend python -m pytest --no-cov \
  backend/tests/test_data_contracts.py \
  backend/tests/test_access_contracts.py \
  backend/tests/test_consumer_contracts.py
```

# Core data pipelines (Phase 3)

`app.jobs.core_operations.core_operations()` supplies reusable NHL reference,
profile, roster, identity-mapping, and basic-statistics operations, Cap Space
contracts with a verified CapWages fallback, current/recent USA Today transactions,
and conservative roster reconciliation. Accepted signings/extensions atomically
include contract-refresh requests. Source failures, coverage gaps, and uncertain
identities/status changes preserve accepted state.

See [core pipeline configuration and source policies](../docs/core-data-pipelines.md)
for runtime injection, source precedence, coverage limits, and an offline setup
demonstration. Games, MoneyPuck, and EDGE are implemented through the separate
Phase 4 registry below; database integration is Phase 6 locally and Phase 9 on AWS. No recurring schedules
are enabled.

# Game, MoneyPuck, and EDGE pipelines (Phase 4)

`app.jobs.game_data_operations.game_data_operations()` registers independently runnable
NHL schedules and completed-game details, MoneyPuck statistics and streamed shot
archives, and dated NHL EDGE summaries/breakdowns. Optional audited EDGE samples
remain explicitly limited. Coverage evidence, correction lookbacks, missing-player
discovery/replay, and atomic recovery use the existing executor.

See [configuration, coverage, and source limitations](../docs/game-tracking-pipelines.md)
for the offline CLI and runtime integration. Database population, live schema and
coverage audits, and AWS consumer integration remain Phase 9 gates; local adapters/query work is Phase 6.

```bash
PYTHONPATH=backend python3 -m pytest backend/tests/test_game_data_sources.py --no-cov
```

# Replacement execution foundation (Phase 2)

API and replacement setup/job entrypoints now share structured backend logging.
Set `LOG_LEVEL=INFO` (or `DEBUG` for batch/checkpoint details). Logs use stderr;
in `ENV=dev`, optional `LOG_FILE=logs/backend.txt` also saves rotating text logs
under `backend/logs/`. CLI summaries use stdout. See [backend logging and failure diagnosis](../docs/backend-logging.md)
for request/run IDs, sanitized errors, configuration, and offline examples.

Setup/population and independent job entrypoints now reuse a shared executor.
It validates source candidates, retains provenance and review issues, isolates
execution environments, reserves conflicting datasets, and atomically commits
accepted batches with run counters and independent checkpoints. It supports
selected reruns, backfills, correction refreshes, failed-batch resume, bounded
source requests, and validation-only setup with no writes.

[Execution foundation usage and recovery](../docs/execution-foundation.md)
includes runnable offline demonstrations and the infrastructure/source adapter
boundaries. Source operations are injected; unimplemented jobs report `deferred`
and exit unsuccessfully. Core source adapters are implemented in Phase 3; selected
database connections,
production locks, and recurring schedules remain later phases.

```bash
PYTHONPATH=backend python3 -m app.database_setup.run_setup \
  --environment dev --current-season 2026 --first-season 2026 \
  --jobs teams_seasons player_profiles team_rosters \
  --runtime tests.execution_fixtures:create_runtime --validation-only
```

The fixture runtime uses an in-memory test store, accepts `dev` only, and makes
no network requests. Existing supported ingestion commands remain available.

# Contract ingestion

Current/recent contracts come from CapWages' active-player index. Historical
gaps are filled by a schema-native source cascade that targets the database's
missing player-seasons directly: CapSpace by NHL ID first, then CapWages when
the first source has no contract covering a requested season.

```bash
PYTHONPATH=backend ENV=dev DATABASE_URL=postgresql://... \
  python -m app.ScriptingFiles.FullDataScript.capspace --dry-run
PYTHONPATH=backend ENV=dev DATABASE_URL=postgresql://... \
  python -m app.ScriptingFiles.FullDataScript.capspace --apply --first-season 2008
```

CapSpace pages are addressed directly with the NHL ID stored in
`player_external_ids`. CapWages profiles with an embedded NHL ID must match it;
older profiles must pass canonical name, slug, and overlapping NHL-stat-season
checks. Contracts and source snapshots retain the source that supplied them. A
profile is fetched once even when several seasons are missing. Apply runs fetch
and commit 100-player batches by
default, use PostgreSQL bulk inserts for source snapshots and new
contract-season rows, and retain previously committed batches if a later
batch fails. Adjust the batch size with `--batch-size`; the HTTP worker cap is
eight. Run the dry-run and local Pavel Datsyuk smoke case
(`--nhl-id 8467514`) before any production rollout. Production commands must
be run only after reviewing the local coverage report; this repository never
connects to production as part of tests or development.

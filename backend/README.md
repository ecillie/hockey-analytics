# TradeValue backend API

The backend is a read-only FastAPI service backed by an Alembic-managed
PostgreSQL schema. It implements every route in `docs/api-contract.md`,
including player and team browsing, Hockey Value, contracts, cap estimates,
search, overview aggregates, and comparison.

## Local development

From the repository root:

```bash
uv sync --locked --all-groups
cp backend/.env.example backend/.env
uv run python -m alembic -c backend/alembic.ini upgrade head
cd backend
uv run uvicorn app.main:create_runtime_app --factory --reload
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
uv run pytest -q tests/backend tests/ml
```

The API service receives an `ApiRepository`; `SqlApiRepository` owns parameterized
queries and validates database rows into immutable values. The July 1 calendar
primitive is shared with ingestion in `app.shared.calendar`. Calendar visibility
and buried-contract relief live in `app.api.policy`, response conversion in
`app.api.util`, and typed failures in `app.api.errors`. HTTP routes own request
validation and preserve the shared error envelope. In-memory repositories and
fixture plugins live in `app.api.tests`, which is excluded from wheels and
runtime artifacts.

The 100% line-and-branch gate covers the service and its extracted behavior:

```bash
uv run python -m coverage report --include='backend/src/app/api/service.py,backend/src/app/api/repository.py,backend/src/app/api/policy.py,backend/src/app/api/util.py,backend/src/app/api/errors.py,backend/src/app/shared/calendar.py' --fail-under=100
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
  uv run python -m alembic -c backend/alembic.ini upgrade head
TEST_DATABASE_URL=postgresql://localhost/tradevalue_test \
  uv run pytest -q tests/backend/test_postgres_integration.py
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
  uv run python -m alembic -c backend/alembic.ini upgrade head
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
# Contract ingestion

Current/recent contracts come from CapWages' active-player index. Historical
gaps are filled by a schema-native source cascade that targets the database's
missing player-seasons directly: CapSpace by NHL ID first, then CapWages when
the first source has no contract covering a requested season.

```bash
ENV=dev DATABASE_URL=postgresql://... \
  uv run python -m app.ScriptingFiles.FullDataScript.capspace --dry-run
ENV=dev DATABASE_URL=postgresql://... \
  uv run python -m app.ScriptingFiles.FullDataScript.capspace --apply --first-season 2008
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

The runtime entrypoint is `app.main:create_runtime_app` with Uvicorn's `--factory`
flag. It loads a single environment snapshot, validates HTTP and database
settings, and returns the application. FastAPI lifespan startup creates the
engine and session factory; shutdown disposes the engine. Each request owns
and closes its SQLAlchemy session. Existing pooling, LIFO/pre-ping, recycling,
and connection-timeout settings are retained.

`create_app()` builds a configuration-independent application for schema
inspection or tests. It accepts explicit frozen settings and an injectable
resource factory; it does not read dotenv files or create an engine. Database
requests need runtime settings or an explicit service override.

`load_environment()` merges dotenv values with exported variables without
changing the process environment, including interpolation precedence. Settings
parsers also accept explicit mappings, and configuration failures identify the
field and reason without including the database URL. DB-API helpers accept
explicit settings; their command-boundary defaults resolve settings when called,
rather than on module import. ML database loaders own and dispose their engine
through a scoped context.

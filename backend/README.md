# TradeValue backend API

A read-only FastAPI service backed by PostgreSQL. It serves players, teams,
statistics, Hockey Value, contracts, cap estimates, search, and comparisons.
See the [API contract](../docs/api-contract.md) for endpoints and response shapes.

## Local development

Run from the repository root:

```bash
uv sync --locked --all-groups
cp backend/.env.example backend/.env
```

Edit `backend/.env` with your local database credentials, then run:

```bash
uv run python -m alembic -c backend/alembic.ini upgrade head
uv run uvicorn app.main:create_runtime_app --factory --reload
```

- API: `http://localhost:8000`
- Interactive docs: `http://localhost:8000/docs`
- Health: `curl http://localhost:8000/api/health`

Health checks database connectivity; an unavailable database returns HTTP 503
with `DATABASE_UNAVAILABLE`. The API never creates or migrates tables on startup.

## Configuration

Use `ENV=dev`, `nonprod`, or `prod`. Dev accepts local `DB_*` components or a
connection URL. Deployed environments use `DATABASE_URL` or the matching scoped
URL (`NONPROD_DATABASE_URL` or `PROD_DATABASE_URL`); scoped URLs take precedence.
See [database setup](database/README.md#initial-setup).

Exported variables override dotenv values. Source installations default to
`backend/.env`; `TRADEVALUE_ENV_FILE` selects another file. Deployed applications
use exported settings and do not bundle dotenv files. Configuration loading does
not mutate the process environment or include database URLs in error messages.

Application logging is disabled in nonprod and prod. In Dev, `LOG_LEVEL`
defaults to `INFO` and `LOG_FORMAT` to `json`; use `DEBUG` for more detail or
`text` for terminal output. Restart after changing Python settings. See
[logging configuration and events](../docs/logging-events.md).

## Frontend connection

Create `frontend/.env.local`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCK_API=false
```

Set backend `CORS_ORIGINS` to the exact browser origins, separated by commas.
Use a narrowly scoped `CORS_ORIGIN_REGEX` for preview URLs. Restart the frontend
dev server or rebuild a hosted frontend after changing its environment.

Responses carry a generated `X-Request-ID`, exposed to allowed origins through
CORS. Caller-supplied IDs are ignored. Logs use route templates and safe fields;
raw URLs, bodies, query strings, and credentials are excluded.

## API behavior

- A season becomes available on July 1 of its start year. The same cutoff
  controls the default season, `/api/seasons`, and season validation.
- Hockey Value uses canonical all-situations advanced stats and the
  position/season replacement level. Next-season projections stay `null`
  unless the stored prediction explicitly supplies `predicted_hockey_value`.
- Missing values stay `null`. Money is integer cents; percentages are ratios.
- Each request owns and closes its session. The lifespan hook creates database
  resources and configures logging, then disposes the engine on shutdown.
- `create_app()` supports schema inspection and injected test resources without
  reading configuration or opening a database. Runtime serving uses
  `create_runtime_app()`.

## Tests

Run from the repository root:

```bash
uv run pytest -q tests/backend tests/ml
```

Use only a disposable database named `tradevalue_test...`: integration fixtures
truncate tables. The [verification guide](../docs/python-verification.md) covers
setup, unit-only runs, coverage, and approved framework boundaries.

CI verifies migration upgrade/no-op/downgrade cycles, schema catalogs, API smoke
checks, packages, and the 100% API/calendar coverage gate. Ingestion tests use
saved fixtures rather than live upstream services.

## Data collection

Run loaders separately from the API, after migrations. The
[ingestion guide](src/app/ScriptingFiles/FullDataScript/README.md) documents the
full pipeline, roster refresh, historical contract recovery, and team-stint repair.
[Command options and exit codes](../docs/python-commands.md) are listed separately.

Stages track their state in `ingestion_runs` and use advisory locks to prevent
concurrent copies. Validation precedes writes; upserts retain rows absent from
later snapshots. An incomplete roster feed rolls back its update. Historical
contract batches retain earlier commits if a later batch fails.

The default source checks expect MoneyPuck seasons 2008–2025, at least 30 NHL
teams, 500 active NHL players, 100 regular-season schedule games, and a 98%
CapWages profile success rate. Tests lower volume requirements for small fixtures.
Review local contract coverage and dry-run results before a production load.

Historical CSVs live in `backend/data/`; `TRADEVALUE_DATA_DIR` overrides that
location. Retired loaders under [legacy_loaders](legacy_loaders/README.md) are
non-executable recovery references, not database backups.

## Container and deployment

From the repository root:

```bash
docker build -t tradevalue-api backend
docker run --rm -p 8000:8000 --env-file backend/.env tradevalue-api
```

The image runs as a non-root user and excludes ingestion code and local source
data. Its database must be reachable from inside the container. CI smoke-tests
health, seasons, and teams against a disposable PostgreSQL service.

For Vercel, use root directory `backend`; deploy the frontend as a separate
project rooted at `frontend`. Use pooled Neon URLs for API requests and direct
URLs for migrations and ingestion. Keep every database URL out of the frontend.

Follow the [deployment guide](../docs/deployment-vercel-neon.md) and
[release workflow](../docs/ci-promotion.md) for environment variables, migration
approval, and manual production promotion.

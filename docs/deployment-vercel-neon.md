# Deploying TradeValue on Vercel and Neon

TradeValue deploys as two Vercel projects backed by one Neon Postgres database.
The API and web app are intentionally separate so each directory is detected and
built with its native framework.

## 1. Create Neon

The preferred path is to add Neon from the Vercel Marketplace while configuring
the backend project. You can also create the database directly in Neon.

Keep two connection strings:

- `DATABASE_URL`: the pooled Neon URL whose hostname contains `-pooler`; use it
  for the deployed backend.
- `NEON_DIRECT_DATABASE_URL`: the direct URL; keep it outside the frontend and
  use it for schema changes and ingestion.

Initialize an empty database from a trusted local environment:

```bash
uv sync --locked --no-default-groups
DATABASE_URL="$NEON_DIRECT_DATABASE_URL" \
  uv run python -m alembic -c backend/alembic.ini upgrade head
DATABASE_URL="$NEON_DIRECT_DATABASE_URL" \
  uv run python backend/database/schema_snapshot.py
```

For databases previously created from `schema.sql`, follow the verified
one-time stamping procedure in `backend/database/README.md`; do not run the
initial migration over existing tables.

Then load the source data if the database has not already been populated:

```bash
uv sync --locked --all-groups
cd backend
DATABASE_URL="$NEON_DIRECT_DATABASE_URL" ENV=prod \
  uv run python -m app.ScriptingFiles.FullDataScript.run_all
```

Do not run the ingestion pipeline inside the request-serving Vercel Function.

## 2. Create the backend Vercel project

Import the Git repository and configure:

- Root Directory: `backend`
- Framework: FastAPI (also pinned by `backend/vercel.json`)
- Production branch: `Prod`, if retaining the repository's promotion workflow

Add these Production variables:

```dotenv
ENV=prod
LOG_LEVEL=INFO
LOG_FORMAT=json
DATABASE_URL=postgresql://...-pooler....neon.tech/...?...sslmode=require
CORS_ORIGINS=https://YOUR_FRONTEND_PRODUCTION_DOMAIN
```

For Preview deployments, use a separate Neon branch where possible. Set
`ENV=nonprod`, `DATABASE_URL` to that branch's pooled URL, and configure the same
production origin plus a narrowly scoped preview regex:

```dotenv
CORS_ORIGINS=https://YOUR_FRONTEND_PRODUCTION_DOMAIN
CORS_ORIGIN_REGEX=^https://YOUR_FRONTEND_PROJECT(-[a-z0-9-]+)?\.vercel\.app$
```

Deploy, then verify:

```bash
curl https://YOUR_BACKEND_DOMAIN/api/health
curl https://YOUR_BACKEND_DOMAIN/api/seasons
```

## 3. Create the frontend Vercel project

Import the same Git repository again and configure:

- Root Directory: `frontend`
- Framework: Vite (also pinned by `frontend/vercel.json`)
- Production branch: `Prod`

Add these variables to Production and Preview:

```dotenv
VITE_USE_MOCK_API=false
VITE_API_BASE_URL=https://YOUR_BACKEND_DOMAIN
VITE_LOG_LEVEL=INFO
```

These variables are compiled into the browser bundle, so changing them requires
a new frontend deployment. `DATABASE_URL` must never be configured on the
frontend project.

Browser diagnostics stay in the user's developer console; this release does not
send them to a hosted collector. `VITE_LOG_LEVEL=DEBUG` requires a new build and
adds safe request lifecycle records. Restore `INFO` with another build after
troubleshooting. This setting is independent of Preview/Production selection and
mock/live data. Only validated `X-Request-ID` values correlate browser failures
with API logs. Never copy raw response bodies, search terms or credentials into
diagnostics. See [the logging inventory](logging-events.md) for emission limits.

## 4. Validate the release

Before deploying schema-dependent code, run the GitHub Actions
`Database migration` workflow for `nonprod` from the current `Release-x.y.z` or
`Hotfix-x.y.z`
branch. The selected GitHub Environment must contain a direct, non-pooled
`DATABASE_URL`. After validation, run it for
`prod`; configure required reviewers on the GitHub `prod` Environment so this is
a gated operation. The workflow serializes migrations per environment, applies
the current Alembic head with lock and statement timeouts, verifies the catalog,
and runs database-backed API smoke checks. It never runs from application
startup.

After both deployments succeed:

1. Open the frontend production URL and refresh directly on `/players`.
2. Confirm seasons, players, teams, search, and a player detail page load.
3. Confirm the browser console has no CORS or mixed-content errors.
4. Confirm unknown player and team URLs show application-level not-found states.
5. Review backend Function logs for database connection or timeout errors.

Git-based deployments handle builds automatically. The repository CI workflows
still run unit tests, lint, and the frontend production build before promotion.
The `Dev`, `Release`, and `Prod` workflows each publish an environment-specific
`required` check. Configure those checks as branch requirements and enable the
release PR routing and manually merged Prod promotions by following
[CI and automatic promotion setup](./ci-promotion.md).

## Installed API distribution

The Vercel project root remains `backend/`, and `index.py` imports the installed
`app.main` package. Generated `backend/requirements.txt` pins runtime dependencies
and ends with `.` to build and install the backend distribution from that root.
It works without a workspace lockfile or editable installation in the deployment
context. Keep this fallback until the hosted builder's workspace discovery has
been verified. `pyproject.toml` excludes `src/app/ScriptingFiles` from both the
runtime wheel and source distribution; ignore rules exclude jobs, datasets,
and archived loaders from upload, and `excludeFiles` removes source trees from
the final function. Docker installs the same distribution and removes its build
sources. No ML or development dependencies enter these API artifacts.

The migration workflow uses the locked `migration` group for its HTTP smoke
client. For an equivalent local operational environment, use
`uv sync --locked --no-default-groups --group migration` and prefix commands with
`uv run --no-default-groups --group migration python`.

## Logging startup ownership

The API installs its shared process logging policy in the owner-approved FastAPI
lifespan startup hook, before database resources are created. Docker's factory
and the Vercel ASGI export supply the same validated settings. Imports and schema
generation do not install handlers. `LOG_LEVEL` defaults to `INFO` independently
of `ENV`; `DEBUG` adds application diagnostics. `LOG_FORMAT` accepts `json`
(default) or `text`. Exported variables override dotenv. Invalid/empty settings
fail before database settings are resolved. Restart or redeploy after changing
settings, and restore INFO after troubleshooting. No schema change is needed to
roll back logging settings or the application artifact.

Container stderr is available through the hosting service's process logs.
Vercel captures application output in Runtime Logs. Its FastAPI documentation
supports lifespan startup/shutdown, but states shutdown output is not retained
in the dashboard and shutdown cleanup is limited to 500 ms. Do not depend on
shutdown events as hosted delivery confirmation. Platform retention, permissions
and deployed sink limits must be verified during release acceptance; local
stdout/stderr captures do not establish hosted retention.

Reference: [Vercel FastAPI startup and shutdown](https://vercel.com/docs/frameworks/backend/fastapi#startup-and-shutdown).

## API correlation and failure ownership

All API responses include a newly generated `X-Request-ID`; allowed browser
origins can read it through CORS, including on error responses. Search the
JSON `request_id` field in request summaries and exception diagnostics rather
than copying URLs, headers or bodies into incident logs. INFO records completed
requests, failed health checks, readiness and successful shutdown. DEBUG adds
request-start, successful health and expected cancellation events. Database and
unexpected request failures produce one safe exception diagnostic; invalid
requests and missing resources use access summaries. A response may already have
status 200 when a streaming failure occurs: use `outcome=failed` and the matching
request diagnostic rather than interpreting status alone.

The application does not buffer streaming bodies or change framework exception
identity. Uvicorn's duplicate traceback is suppressed only for the matching
already reported error, once; unrelated host errors remain visible. Other
propagated failures retain safe request context for the host diagnostic.
The API disables Uvicorn's access stream and preserves host handler objects
while applying safe formatting. Root platform logging is left in place; API
and coordinated Uvicorn events avoid propagating raw messages/tracebacks to it.

Database settings are validated during startup after safe logging installation,
using the immutable environment snapshot captured by the factory. Invalid URLs
cannot escape through a pre-logging database validation traceback. Lifespan
failures send validated, bounded type/frame snapshots through the ASGI failure
message, retaining the original exception and preventing raw traceback strings
from reaching the host. Startup failure is CRITICAL; shutdown failure is ERROR.
Expected cancellation is DEBUG, except when a genuine secondary cleanup failure
also requires an error diagnostic. No exception message, cleanup note, local,
SQL parameter or model payload is serialized.

The official [Vercel Python runtime source](https://github.com/vercel/vercel/blob/main/python/vercel-runtime/src/vercel_runtime/vc_init.py)
uses vendored Uvicorn for ASGI lifespan, with access logging disabled and
`log_config=None`. Its root IPC handler can render raw exception text, which is
why application/Uvicorn events use the safe stderr path without replacing the
platform root handler. The local Docker/ASGI probes verify this ownership design;
actual deployed log retention, limits and delivery still require phase-5 hosted
acceptance. Do not infer those settings from a successful preview build.

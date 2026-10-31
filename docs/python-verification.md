# Python verification

The supported runtime is Python 3.12. Install the root uv workspace with
`uv sync --locked --all-groups`. Runtime, ingestion, ML, and development
requirements are generated from the same lock. Run these checks at the root:

```bash
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest
```

## Test selection and resource ownership

`unit` and `integration` are registered, strict pytest markers. PostgreSQL tests
carry explicit integration marks. Collection rejects a test that depends on the
disposable database fixture without that mark; other tests receive `unit`.
The harness initializes scikit-learn during bootstrap, before collection; this
allows its upstream OpenMP defaults to initialize once. Collection reads no
database configuration and changes no process environment.

Run unit tests without database configuration or dotenv loading:

```bash
env -u DATABASE_URL -u DEV_DATABASE_URL -u TEST_DATABASE_URL \
  ENV='' TRADEVALUE_ENV_FILE=/dev/null uv run pytest --no-cov -m unit -q
```

An autouse fixture rejects socket connections in unit tests. Saved responses,
behavioral repositories, and scripted transports replace external services.
Fresh-process help/import tests execute only configuration-independent entry
points. Resource-lifetime tests may use an in-memory SQLite engine. Unit tests
never require PostgreSQL or live upstream feeds. CI runs this isolated selection
before the complete coverage run.

Integration tests require a newly created disposable PostgreSQL database. Test
fixtures truncate application tables. The shared fixture parses the URL and
requires its database name to start with `tradevalue_test`; a missing URL skips
only the integration selection, and an unsafe URL fails setup. The session
fixture temporarily sets both generic and development-scoped application URLs
to this disposable target and restores the environment afterward.

For example, after starting a dedicated PostgreSQL 15 container on port 55432:

```bash
export TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/tradevalue_test_phase12
export DATABASE_URL="$TEST_DATABASE_URL"
export DEV_DATABASE_URL="$TEST_DATABASE_URL"
export ENV=dev
export TRADEVALUE_ENV_FILE=/dev/null
uv run python -m alembic -c backend/alembic.ini upgrade head
uv run pytest --no-cov -m integration -q
uv run pytest -q
```

The complete run must finish without skips. Selecting only integration tests
with `--no-cov` is useful for diagnosis; the complete run supplies the aggregate
coverage gate. The migration lifecycle test creates a second uniquely named
database, exercises unsafe-schema rejection, offline SQL, repeated upgrade,
catalog equality, API/reference-data smoke, and downgrade/re-upgrade, then drops
that database in cleanup. Never use a development dataset or hosted database.

## Fixture and artifact boundaries

Executable tests live in root `tests/backend` and `tests/ml`. Shared fakes,
scenario bundles, and Hypothesis strategies live in concept `tests` packages
inside `backend/src/app` and `ml/src/ml`. Fixture plugins are registered explicitly
in conftest files. Function-scoped scenarios give each test its own mutable
frames and resource probes; frozen collaborator bundles keep those resource
identities stable. Probe histories deliberately record observable calls and
cleanup, while production domain snapshots use immutable values.

HTTP fakes reject unexpected requests and return saved payloads. SQL catalog
fakes answer supported catalog queries and reject unknown SQL. Assertions cover
outcomes, rollback, ownership, retry bounds, and serialized contracts. The
remaining parser spy checks the regression that a successful CapWages response
is parsed only once. Fresh-process import checks intercept resource constructors
to prove import isolation.

Coverage measures application and ML source plus backend operational and
migration code. Only test-support packages are omitted. Archived `.py.txt`
loaders are non-executable references. The branch-aware aggregate floor remains
58.80%; the separate API service/repository/policy/util/errors/shared-calendar
gate remains 100%. Reports are written under `coverage/python`.

Both wheel and source-distribution configurations exclude test support. Verify
wheel contents, install both wheels in a clean Python 3.12 environment, and
import them from outside the checkout:

```bash
bash scripts/verify-packages.sh
bash scripts/export-requirements.sh --check
uv run python backend/export_openapi.py --check
uv run python -m ml.evaluation.gate
```

The API artifact also excludes ingestion scripts, datasets, training code, and
local configuration. The ML artifact retains its published metadata resource.
The package verifier runs the committed model gate from the installed artifact.

## Framework boundaries

`backend/index.py` retains Vercel's exported `app = create_runtime_app()` ASGI
instance. This is the sole application-owned mutable module export; settings,
routers, engines, and sessions are otherwise composed through factories and
owned lifetimes. The owner merged this retained entrypoint in
[PR #132](https://github.com/ecillie/hockey-analytics/pull/132).

Alembic consumes immutable revision identity and module descriptions. Its
environment invokes the migration composition function when Alembic loads the
file, while configuration and logging are resolved inside that function. Frozen
SQL and revision identifiers are preserved. FastAPI/Pydantic schema inheritance
and route type aliases serve their framework contracts; published uppercase
HTTP enum values stay explicit to preserve OpenAPI and JSON compatibility.

## Full acceptance

Backend CI also builds the production Docker image and runs health, seasons,
and teams HTTP smoke checks against the disposable database as its non-root
runtime user. Frontend CI verifies generated API types, lint, all tests at its
100% coverage thresholds, and the production build. Root test, workspace,
lockfile, and workflow changes select all affected CI jobs. Review the draft
phase PR's checks before merging; production promotion remains manual.

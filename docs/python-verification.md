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
export TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/tradevalue_test_local
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

Database transactions and engine lifetimes retain the original operation or
construction failure when rollback, close, or disposal also fails. Cleanup
attempts continue in order; secondary failures are attached as exception notes.
A cleanup failure with no earlier failure propagates itself. The same small
cleanup helper serves ingestion tracking, including cancellation and interrupt
paths. Failure-injection regressions verify exception identity, original cause,
notes, and attempted cleanup order.

Contract reconciliation and writes share a frozen context whose season bounds
derive from the selected seasons. Embedded profile JSON is decoded once within
each parsing attempt and shared by identity checks and contract extraction.
Later attempts receive detached snapshots; no exposed mutable cache is retained.

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

## Approved framework and test boundaries

The owner approved these narrow exceptions on 2026-11-01. They do not permit
import-time bootstrap in ordinary libraries or additional logging owners.

- **F1 — Vercel:** `backend/index.py` exports `app = create_runtime_app()` and
  resolves environment/dotenv settings at framework load. Database resources
  and logging handlers remain owned by the API lifespan hook.
- **F2 — Alembic:** `backend/migrations/env.py` calls `main()` when the framework
  loads it, returns control on success, and raises `SystemExit` only for a
  nonzero exit code. Configuration and logging are resolved inside that owner.
- **T1 — Test support:** the exact native fault operations below intentionally
  raise to exercise failures. Application invariant policies still return
  violations; this grants no production raise-only helper exception.
- **H1 — Initial migration:** the owner authorized the Python-only path,
  checksum-validation and cursor-cleanup repair in revision `20260910_0001`.
  Frozen SQL, checksum and revision metadata remain unchanged. This grants no
  permission to edit other applied revisions or change schema/data; see the
  [migration development rules](../backend/database/README.md#migration-development).

T1 covers these source-only operations, excluded from distribution artifacts:

- `contracts/tests/fakes.py`: `reject_resource_access`, `FailingRun.succeed`,
  `FailingRun.fail`, `FailedTrackingScenario.ingest`,
  `FailedControlConnection.cursor` (under `app/ScriptingFiles/FullDataScript`).
- `app/shared/observability/tests/fakes.py`: `HostileValue.__str__`,
  `HostileValue.__repr__`, `MetadataAccessError.__dict__`, `BrokenStream.write`,
  `BrokenStream.flush`, and `parse_source_number`, which calls native `int` on
  invalid text to produce a real conversion traceback.
- `app/shared/tests/fakes.py`: `FailingAction.__call__`, `reject_network_access`.

FastAPI/Pydantic schema inheritance and route type aliases serve their framework
contracts. Published uppercase HTTP enum values preserve OpenAPI and JSON
compatibility.

## Release checks

Backend CI also builds the production Docker image and runs health, seasons,
and teams HTTP smoke checks against the disposable database as its non-root
runtime user. Frontend CI verifies generated API types, lint, all tests at its
100% coverage thresholds, and the production build. Review the PR checks before
merging; [production promotion remains manual](ci-promotion.md).

Historical implementation plans, source-digest ledgers and per-run evidence are
available in Git history. Current test results belong to the PR's CI runs.

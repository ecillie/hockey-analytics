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

## ML metadata follow-up, phase 1

The follow-up starts from `Release-1.0.1` at
`762751f590c750ae956783f5a2537c4e563b663b`, which includes the merged original
phase 12. Its scope is F01 in ML, F03, and the ML portion of F11 in `plan.md`.
Other follow-up findings remain separate work.

`validate_metadata`, `validate_committed_model_metadata`, and `load_model` now
return validated `ModelMetadata` values. Read fields as attributes, including
`metadata.metrics.test.mae`. Both split containers and their metric values are
frozen, and feature collections are tuples. Parsing detaches caller-owned JSON
containers. `TrainingResult.metadata_value` retains this typed representation;
its existing `metadata` property returns a detached JSON-compatible snapshot,
and `metadata_json` retains the canonical sorted JSON format. Training split
evaluation returns `SplitMetrics`. `Split` and `Metric` retain the published
`train`/`validation`/`test` and `mae`/`rmse`/`r2` strings.

Metadata policies return structured violations for feature order, temporal
order, and supported model identity. ML-owned failures have dedicated exception
types with keyword context fields; existing ValueError, TypeError,
RuntimeError, and AssertionError categories remain compatible. Pydantic retains
its own schema-validation errors. This change adds no dependency and changes
neither committed metadata values, model calculations, nor OpenAPI.

Regression coverage checks nested immutability and source aliasing, the exact
canonical serialization of committed metadata, strict rows and seasons, split
membership, feature order, model identity, finite metrics, regression directions
and tolerances, failure context, and train/save/load/evaluate round trips.
The local acceptance record is maintained in `plan.md`; verification uses the
commands and unchanged coverage gates above, a dedicated disposable PostgreSQL
15 database, isolated units, installed wheels, and an API container smoke.

Local phase-1 acceptance on Python 3.12/PostgreSQL 15: 675 tests passed with
zero skips, 91.44% aggregate coverage, and 100% API/shared-calendar coverage.
Isolated units passed 628 tests with 47 integration tests deselected. Ruff,
formatting, ty, model/OpenAPI/export gates, isolated wheel checks, Docker build,
and health/seasons/teams HTTP smoke passed. No frontend boundary changed.

## Options and source identity follow-up, phase 2

The follow-up starts from `Release-1.0.1` at
`30d03d65b7e7a865be71f98e4c27ef191a941941`, containing merged phase-1 PR #150.
It addresses F02, F04, and F09 in the local remediation plan.

Source quality checks compose the existing `CountPolicy` with a separate
`DuplicateRatioPolicy`, returning count failures before ratio failures.
Historical contract defaults live in `HistoricalContractOptions`; its owned,
frozen `HistoricalContractLimits` supplies worker and batch ceilings to
validation. Existing compatibility constants derive from these options and
`ProfileHttpOptions`. CLI defaults come from one options instance. Historical
seasons remain 2008–2025, with four workers and a batch size of 100; default
ceilings remain eight workers and 1,000 players per batch. Candidate and coverage
query defaults use the same authority. Explicit overrides remain supported.

Replacement calculations retain their effective percentile in the returned
DataFrame’s `attrs["replacement_percentile"]` metadata. Diagnostics use that value,
including an explicit argument taking precedence over configured options, and
fall back to the default for externally supplied frames without the attribute.
Calculations and output columns remain unchanged.

NHL and MoneyPuck persistence identities now use validated integer player IDs.
MoneyPuck also canonicalizes integer grain fields during deduplication, so
`7`, `7.0`, `"0007"`, `"7.0"`, and `"7e0"` share one identity and grain. The last
original row still wins, with its unmodified source hash; canonicalization does
not rewrite source payloads. Alias rows contribute to duplicate counts and can
therefore trigger existing quality thresholds. PostgreSQL tests verify both
skater and goalie identity linking in the existing MoneyPuck-to-NHL ingestion
order, one stat grain per source, and repeat-ingestion idempotence.

Existing persisted aliases are not merged or rewritten. Any historical data
repair requires a separate collision audit and reviewed operation. No hosted
data or live upstream feeds are used for verification.

Local phase-2 acceptance on Python 3.12/PostgreSQL 15: 706 tests passed with
zero skips, 91.69% aggregate coverage, and 100% API/shared-calendar coverage.
Isolated units passed 657 tests with 49 integration tests deselected. Ruff,
formatting, ty, model/OpenAPI/export gates, isolated wheel checks, Docker build,
and health/seasons/teams HTTP smoke passed. Both verification containers were
removed after acceptance.

## Operational commands follow-up, phase 4

This phase starts from `origin/Dev` at
`8fe9fef` after persistence-context PR #155 merged. Feature PRs target `Dev`.

Operational commands and Alembic share explicit database URL selection:
`DATABASE_URL` takes precedence over `TEST_DATABASE_URL`; a missing or exactly
empty primary falls back, and missing/empty values for both fail with structured
configuration details. Whitespace is retained by these operational commands,
matching their existing behavior. Runtime application settings retain their
separate scoped URL and trimmed component/default rules. An explicitly supplied
empty mapping is never replaced by the process environment. Alembic alone
requires the PostgreSQL URL scheme.

Health and base season-payload checks are shared between HTTP container and
migration smoke commands. Migration smoke still requires a current season of
at least 2005, no teams, and the exact seeded reference data. Container smoke
still accepts populated teams and retries readiness within its configured
budget. Readiness errors carry the last failure as their explicit cause; smoke
response errors expose operation, path, status, and response body.

Both ingestion entrypoints use one exception handler, retain their distinct
incomplete-feed diagnostics and exit code 2, and log general failures once with
exit code 1. Help and invalid options still exit before opening resources;
success still emits one JSON document. Missing schemas, unavailable cached
source snapshots, and reversed backfill season ranges now have dedicated errors
with typed fields. Pydantic validator errors and frozen migration-revision
failure behavior remain governed by their existing boundary contracts.

Backfill rollback/close, plus preflight and snapshot engine disposal, use the
shared cleanup helper. A repair or commit failure remains the identical raised
exception with its original cause; secondary cleanup failures appear in notes,
and close still runs. Cancellation and interruption also complete cleanup.
Cleanup-only failures propagate. The schema catalog now has a named type alias.

Local acceptance used Python 3.12.14 and a dedicated PostgreSQL 15 database
`tradevalue_test_followup04`: **738 passed, zero skips**, **91.43%** aggregate
coverage in **63.77 seconds**, with **100%** API/shared-calendar coverage.
Seventeen new cases cover missing/empty/configured URL selection, intentional
runtime empty defaults, primary exception identity/cause and cleanup ordering,
readiness failure details, and caller-specific smoke policies. Existing CLI
coverage verifies all supported help, invalid arguments, silent imports, output,
and diagnostic contracts.

Ruff lint/format, ty, OpenAPI parity, the committed ML gate, generated dependency
exports, isolated API/ML wheel installation and wheel/sdist exclusions, the
production Docker build, and health/seasons/teams HTTP smoke passed. No frontend
or serialized API boundary changed. Existing upstream FastAPI/Starlette
warnings remain. No hosted data or live upstream ingestion was used.

With database URLs absent and dotenv disabled, isolated units passed **688**
tests with **50** integration tests deselected in **30.42 seconds**.

## Test organization follow-up, phase 5

Started from `origin/Dev` at `b41bcf3` after operational-command PR #157
merged. Reusable HTTP clients, CLI actions, database probes, scenario values,
repository inspection helpers, and generated ML metric strategies live under
their concept's `src/.../tests` package. Shared fixture plugins also own the
disposable ingestion/contract databases and PostgreSQL API seed/service setup.
The existing conftest plugin registrations load those fixtures explicitly.
Production application code, package exclusions, and test selection rules are
unchanged.

Fixtures used by one test class live in that class. Ingestion transport inputs,
contract services/options, ML input copies, and artifact destinations are
arranged before the test body. Scenario-only parameters now belong to their
fixtures, and unused monkeypatch arguments are removed. Test bodies retain
the operations, failure injection, mutations, and observations being verified.
In particular, the environment-preservation test captures its observation in
the call phase: pytest itself changes `PYTEST_CURRENT_TEST` between fixture
setup and the call, so a setup-phase snapshot tests an unrelated transition.

Collection retains all **738** original test names and parameter IDs, with
**50** integration cases. Some node IDs acquire a class name to support narrow
fixture scope; no case or assertion was removed. Isolated collection succeeds
with database URLs absent, ENV empty, and dotenv disabled. The complete run on
Python 3.12.14 and disposable PostgreSQL 15 database
`tradevalue_test_followup05` passed **738 tests, zero skips**, **91.71%** aggregate
coverage in **67.68 seconds**. The API/shared-calendar coverage gate remains
**100%**. Isolated units passed **688**, with **50** integration cases deselected.

Ruff lint/format, ty, locked workspace sync, committed ML metrics, OpenAPI
parity, dependency exports, isolated API/ML package imports, wheel/sdist test
support exclusions, and the production Docker build passed. The HTTP smoke
gate exercises health, seasons, and teams against the disposable database.
Structural review found no reusable fake classes or ordinary support helpers
remaining in executable test modules, no unused test arguments, and no new
prohibited constructs. Intentional fake failures and owned call histories
remain observable test behavior. This phase closes F07/F14; the remaining
typing/style and final enforcement work remains in phases 6 and 7.

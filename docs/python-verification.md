# Python verification

The ongoing final semantic review is recorded source by source in
[Python semantic audit checkpoint](python-semantic-audit.md). Its ML checkpoint
separates command adapters from domain, repository, service and utility roles,
retains compatibility imports and the published model/CLI contracts, and shares
metric types and position grouping. A borrowed reader Protocol makes dataset
resource ownership explicit. Tests retain fixture-owned mutable observation
probes; immutable domain values do not wrap shared test state.

The ML checkpoint passed **1,208 tests, zero skips**, **90.74%** aggregate
coverage and the **100%** API/calendar selection on fresh database
`tradevalue_test_logging05_roles_final` under Python 3.12.14. Isolated units passed
**1,158**, with 50 integration tests deselected. Lint, format, types, structural
scope, package/export, schema/API smoke and committed-model gates passed. This
does not accept pending source reviews or the newly identified cleanup/HTTP
resource findings; exact framework dispositions and hosted NonProd acceptance
also remain open. Full evidence is in [logging verification](logging-verification.md).

The following cleanup checkpoint fixes note-rendering/attachment failures that
could mask a primary error, and explicitly closes caught HTTP error responses.
Regression scenarios fail before the fixes and preserve original identity,
cancellation, cleanup order and safe diagnostics afterward. Final verification
on fresh `tradevalue_test_logging05_cleanup_final` passed **1,236 tests, zero
skips**, **90.84%** aggregate coverage and the **100%** API/calendar gate.
Isolated units passed **1,186**, with 50 integrations deselected. Static, package,
schema/API, ML and rebuilt INFO/JSON + DEBUG/text image gates passed. The semantic
audit still has 130 nonempty files pending and records the remaining API boundary
and framework decisions explicitly; these results are not final phase-7 acceptance.

The API query checkpoint now constructs PlayerQuery at the validated route and
passes it through service/repository without rebuilding positional arguments.
SummarySelection carries immutable bindings and query options. Existing filter,
pagination, tie/null ordering and injection regressions retain their behavior;
OpenAPI parity passes. Fresh `tradevalue_test_logging05_query_final` passed
**1,236 tests, zero skips**, **90.85%** aggregate coverage and the **100%**
API/calendar gate. Isolated units passed **1,186**, with 50 integrations
deselected. Static, migration/schema/API, package/export, ML and rebuilt
INFO/JSON + DEBUG/text image checks pass. The ledger now records **105**
nonempty files pending and explicit findings from the inspected sources;
hosted NonProd and final acceptance remain open.

The diagnostic snapshot/worker checkpoint retains frozen frame and exception
models with immutable nesting and copies them only for serialization. Native
attribute-fault regressions preserve primary failures and bounded safe output;
broader catches are limited to best-effort metadata access. One worker policy
now applies the same injected limits at validation and execution. Fresh
`tradevalue_test_logging05_snapshots_final` passed **1,253 tests, zero skips**,
**91.00%** aggregate coverage and the **100%** API/calendar selection. Isolated
units passed **1,203**, with 50 integrations deselected. Static, schema/API,
package/export, ML and rebuilt two-mode image gates pass. The audit now records
**90** nonempty files pending, plus explicit findings in inspected sources;
these results do not complete phase 5 or phase 7.

The source-boundary checkpoint makes raw schedule games detached snapshots while
preserving serialization and filtering nonregular games before strict validation.
Durable counts accept only nonnegative plain integers; unsupported stat-kind
strings raise a typed boundary error. CSV file opening moved unchanged to the
repository adapter and its actual caller was updated. Fresh
`tradevalue_test_logging05_source_final` passed **1,269 tests, zero skips**,
**91.01%** coverage and the **100%** API/calendar selection. Isolated units passed
**1,219**, with 50 integrations deselected. Static, schema/API, clean package,
exports and ML gates pass. All supported runtime sources now have content review;
**67** test/support sources and the recorded runtime findings remain unresolved.
The previously verified API image remains applicable because distributed API
code, build/dependency inputs and shared logging are unchanged; this checkpoint
does not claim a new image build or hosted NonProd acceptance.

The resource-edge checkpoint shares primary-preserving cursor ownership across
team-stint queries and cached contract-summary reads, and closes caught roster
HTTPError responses without replacing the original failure. Roster transport
validation moved unchanged into the HTTP adapter; classification uses immutable
per-sync evidence, and native Pydantic validators raise typed compatible errors.
Three disposable-engine fixtures now guard setup before yield and use production
transaction/resource ownership. The final fresh
`tradevalue_test_logging05_resource_edges_final2` run passed **1,317 tests, zero
skips**, **91.20%** coverage and the **100%** API/calendar gate. Isolated units
passed **1,267**, with 50 integrations deselected. Static, package/export,
schema/API, ML and rebuilt INFO/JSON + DEBUG/text image checks pass. The ledger
now has **38** pending test files and explicit helper/verification/role findings;
this is still a checkpoint, not final phase-5/phase-7 acceptance.

The verifier checkpoint removes redundant filesystem resolution from ordinary
inspection-helper imports and moves source discovery into explicit pytest
collection. HTTP probes now validate native response contracts, fresh lowercase
32-hex request IDs and replacement of valid caller IDs. Log probes enforce
per-event severity, mode thresholds, correlation and absence of orphan errors.
Real container captures exercise the verifier itself, including corrupt inputs
previously accepted. Fresh `tradevalue_test_logging05_verifiers_final2` passed
**1,349 tests, zero skips**, **91.20%** coverage and the **100%** API/calendar
gate. Isolated units passed **1,299**, with 50 integrations deselected. Static,
schema/API, clean package/export and ML gates passed. Two-mode container probes
passed against the unchanged verified API image. The ledger has **25** pending
test files and explicit findings in inspected sources; hosted NonProd and final
phase-5/phase-7 acceptance remain outstanding.

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

## Typing and style follow-up, phase 6

Started from `origin/Dev` at `459d446` after PR #159 merged. Roster feed
collections, stored-player collections, normalized identities, and grouped
contract source records now have domain-named PEP 695 aliases. `SchemaCatalog`
already supplied the catalog alias from phase 4. Incidental primitive
containers retain their existing annotations.

Module helpers now describe their operations: parsing, extracting, loading,
building, calculating, selecting, and resolving. Callers and injected CLI
actions use those names. Existing command module paths, HTTP fields, enum and
exit values, SQL, model calculations, frozen revisions, and serialized metadata
remain stable. Compatibility exports retain the established training,
evaluation, metadata, artifact-path, database-context, calendar, and ingestion
entrypoints as direct aliases. Existing CapSpace compatibility reexports remain
available. Pytest fixture names describe injected values; framework hooks keep
their required names.

The remaining ordinary `else` branches were replaced with guards in saved
source transports and the preflight decision test. A shared CapWages response
builder removes repeated saved-HTML serialization. The initial migration's
branch remains frozen with its revision SQL and identifiers.

The disposition review also found that F11's statistics-page dictionaries were
still mutable. `StatsPage` now owns immutable JSON row snapshots, returns
detached dictionaries through `data`, and serializes the original `data` shape.
The NHL adapter captures one detached page value per parsing operation.
Regressions cover nested input aliasing, nested output mutation, frozen storage,
and Python/JSON serialization. Non-JSON objects fail boundary validation before
persistence.

The ML layout review retains `load_player_stats` and `load_salary_cap` as
supported SQL adapter/command modules. Both already accept borrowed connections,
keep owned-resource acquisition explicit, and separate diagnostics from reads.
Adding another forwarding repository layer would not establish a new ownership
or validation guarantee. No module moves or new repository interfaces are part
of this phase. This is the extraction assessment requested by the plan, not an
owner waiver of the global role-layout rule; final rule coverage and exact
framework dispositions remain phase 7 work.

The second-pass finding ledger now has these implementation dispositions:

| Finding | Disposition and behavior evidence |
| --- | --- |
| F09 | Phase 2 canonical identities; generated aliases and real PostgreSQL cross-source/idempotence cases remain selected. |
| F10 | Phases 3–4 shared cleanup; primary failure identity, secondary notes, cleanup order, cancellation, and cleanup-only regressions remain selected. |
| F11 | Phase 1 freezes ML metadata; phase 6 closes the remaining statistics-page snapshot gap with nested mutation and serialization regressions. |
| F12 | Phase 3 shares decoded contract snapshots; phase 6 captures each statistics page's detached rows once. |
| F13 | Phase 4 shares operational URL resolution and common smoke checks; caller-specific restrictions remain covered. |
| F14 | Phase 5 removes unused collaborators and relocates scenario parameters; phase 6 updates fixture targets for renamed operations. |
| F15 | Phase 4 names the schema catalog; phase 6 names remaining repeated roster and contract record shapes. |
| F16 | Phase 6 renames helpers and simplifies remaining branches; supported exports and frozen revision behavior are preserved. |

F01–F08 retain their phase 1–5 implementation records above. This ledger closes
the implementation findings; it does not replace phase 7's complete source
review, rule-evidence mapping, or owner decisions for framework exceptions.
No new blanket exemptions or enforcement configuration were introduced.

Local acceptance on Python 3.12.14 and disposable PostgreSQL 15 database
`tradevalue_test_followup06`: **742 passed, zero skips**, **91.76%** aggregate
coverage in **71.18 seconds**, with **100%** API/shared-calendar coverage.
Isolated units with database URLs absent, ENV empty, and dotenv disabled passed
**692 tests**, with **50** integrations deselected, in **49.29 seconds**.

Ruff lint/format, ty, locked workspace sync, committed ML metrics, OpenAPI
equality, generated dependency exports, isolated API/ML wheel imports and
wheel/sdist exclusions passed. The production image passed health, seasons,
and teams HTTP smoke as uid 10001. No frontend or serialized HTTP boundary
changed. Existing upstream FastAPI/Starlette deprecation warnings remain;
the sandboxed unit run also reported joblib's physical-core detection fallback.
Verification used no hosted data, live upstream feeds, or model replacement.

Whole-tree structural searches and diff review found no new prohibited
constructs or ordinary code comments. A normalized AST comparison isolated
renames from the intended alias, annotation, guard, and snapshot changes;
manual review covered those changes, local-variable shadowing, fixture targets,
serialization, resource ownership, and compatibility exports. Frozen revisions,
OpenAPI, lockfiles, tool configuration, and frontend source are unchanged.

## Initial enforcement work, phase 7

At the owner's request, phase 7 started on `origin/Dev` at `459d446` while
phase 6 PR #161 was still running. After its successful Dev workflow
`41260161286`, repository automation merged phase 6 as `c37922e`. The phase 7
branch then fast-forwarded to current Dev and restored its independent checker
changes without conflicts. No manual merge of the PR was performed.

Run the initial structural gate with:

```bash
uv run python -m backend.database.verify_python_rules
```

The reusable backend CI job runs the same command. It parses application, ML,
operational, migration, and test sources without importing them. Dependency
environments and retired `.py.txt` loaders are outside the executable scope.
Missing source roots, missing registered entrypoint files, and invalid Python
syntax fail the command. A repository-scope test requires every Git-tracked
`.py` file to be included, so adding a new source location requires updating
the scope rather than silently excluding it.

This gate detects explicit lambda expressions, static-method decorators,
literal `while True`, postponed-annotation imports, `Any` imports
from typing packages (including renamed imports), private class declarations,
`__post_init__`, direct `object.__setattr__`, and deletion. Preferences about class methods and
match statements, and the narrower ban on `ClassVar` in dataclasses, remain
manual checks; the gate does not turn those judgments into broader prohibitions.
Regression scenarios include source locations, multiple findings, ordinary
instance methods, bounded loops, text containing forbidden-looking syntax,
and source that must never execute. Command tests cover help, invalid arguments,
failure logging, successful output, and fail-closed source inspection.

The initial evidence map below identifies the verification method; it does
not assert that the final semantic review has been completed.

| Rule family | Automated evidence | Remaining manual acceptance |
| --- | --- | --- |
| Managed runtime and dependencies | Locked uv sync, Python 3.12 CI, export parity, clean wheel installs | Confirm declared runtime and dependency boundaries on the selected final commit. |
| Classes and immutable values | ty; metadata and source-snapshot mutation regressions | Inspect nested state ownership, class responsibilities, method placement, defaults, and constructor effects throughout supported source. |
| Protocols and inheritance | ty; behavioral repositories and adapter tests | Verify minimal runtime-checkable Protocols and every necessary framework inheritance boundary. |
| Typing | Ruff and ty; selected prohibited import checks | Review narrow/repeated types, constrained aliases, qualified/indirect forbidden type access, and context-manager annotations. |
| Control flow | Selected AST bans; pagination and failure-boundary tests | Review branching, nesting, loop exits, walrus opportunities, deliberate truthiness, and indirect equivalents of banned forms. |
| Errors and cleanup | Primary-failure identity/cause, secondary cleanup notes, cancellation, rollback, close and disposal regressions | Review dedicated typed failures, returning invariants, translation boundaries, and intentional test-only raises. |
| Async and external I/O | Lifecycle timeout/shutdown tests; isolated unit network guard | Inspect every await, task lifetime, thread boundary, synchronous I/O call, and external-I/O timeout. |
| Logging and CLIs | Shared CLI behavior scenarios; OpenAPI/import/help tests | Inspect configuration location, lazy diagnostics, one-report behavior, frozen command options, and handler dispatch. |
| Layout and resources | Wheel/sdist exclusions; installed imports; disposable database integration tests | Resolve role-layout assessment and confirm each resource's owner and lifetime. |
| Tests | Unit/integration collection, network isolation, fixture-driven scenarios, package exclusions | Review arrangement placement, fixture scope, meaningful assertions, mutable probes and generated input spaces. |
| Comments, docstrings and names | Ruff formatting; phase 6 naming changes; source/diff searches | Inspect tokenized comments, metadata docstrings, compatibility aliases, and non-mechanical naming decisions. |
| Published behavior | OpenAPI/generated-type parity; API coverage; ML metadata gate; image smoke | Confirm compatibility values and exact frozen migration behavior on the final combined commit. |

Exact owner dispositions remain to be recorded for Vercel's exported mutable
ASGI app in `backend/index.py`, Alembic's load-time bootstrap in
`backend/migrations/env.py`, and intentional source-only test failures that
must raise to protect a boundary. The earlier ML layout assessment also needs
its final disposition. Historical merges are evidence of behavior, not blanket
approval of exceptions to the global rules. The checker adds no allowlist or
waiver for these cases because it does not attempt to automate those judgments.

The complete file-by-file semantic review, final exception decisions, and final
phase 7 acceptance record remain outstanding. Initial checker verification is
recorded separately from that final acceptance.

Initial checkpoint verification on Python 3.12.14 and disposable PostgreSQL 15
database `tradevalue_test_followup07`: **769 passed, zero skips**, **91.88%**
aggregate coverage in **62.70 seconds**, with **100%** API/shared-calendar
coverage. Isolated units passed **719**, with **50** integrations deselected,
in **38.99 seconds**. The 27 added cases exercise structural detection, deliberate
manual-review cases, source scope, non-execution, command exits, and diagnostics.

Ruff lint/format, ty, the structural gate, actionlint 1.7.12, locked sync, ML
metadata, OpenAPI parity, dependency exports, isolated installed packages and
wheel/sdist exclusions passed. Frontend generated-type parity, lint, all 60
tests at 100% coverage, and production build passed. The production API image
passed health/seasons/teams smoke as uid 10001 against the disposable database.
Existing dependency and sandboxed core-detection warnings remain. No hosted
database or upstream ingestion was used for this checkpoint.

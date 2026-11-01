# Logging implementation evidence

## Phase 1 foundation checkpoint

Started `feature/logging-01-foundation` from freshly fetched `origin/Dev`
`4d8fae3`, after verifying prerequisite PR #163 merged and its required Dev
checks and Vercel previews succeeded. The historical local `plan.md` is retained.

This is an unfinished checkpoint, not phase acceptance or a release claim.
The working tree adds independent frozen logging settings, strict normalized
level/format parsing, a bounded safe formatter, safe stderr stream adaptation,
and 18 tests covering settings, generated hostile exception text, unknown
objects/fields, threshold filtering, formatting failures and sink failures.
These helpers do not load dotenv, require database configuration, install a
handler on import, or change any runtime entrypoint yet.

The formatter omits arbitrary message arguments, exception messages, notes,
source lines, absolute filenames and locals. Exception types and stack locations
are retained. Structured context is allowlisted; unknown objects are never
stringified. JSON and text output use single-line JSON escaping. Record limits
default to 8 KiB, 256 characters per identifier, 12 frames and four chained
exceptions. These limits and truncation paths still require additional boundary
verification before acceptance. Hosted sink limits have not been verified.

The owner decision on allowing configuration in the API lifespan startup hook
is pending. The proposed hook serves both Uvicorn and Vercel, leaving ordinary
imports and `create_app()` free of handler installation. Do not treat the
implementation request or prior Python PR merges as an approved exception to
`Only main() configures logging`.

Checkpoint verification on Python 3.12.14 and a new PostgreSQL 15 container,
using only disposable `tradevalue_test_logging01`:

- Locked all-group sync, Ruff check/format, ty and structural gate passed.
- Complete suite: **787 passed, zero skips**, **91.87%** aggregate coverage,
  **45.35 seconds**. API/shared-calendar behavior coverage remains **100%**.
- Isolated units with database URLs absent and dotenv disabled: **737 passed**,
  **50 deselected**, **29.53 seconds**.
- Dependency export parity, OpenAPI parity, isolated API/ML package installs,
  wheel/sdist exclusions and committed ML gate passed.
- New logging modules currently have **91.38%** coverage. This is evidence of
  remaining boundary scenarios, not a declaration of completed logging gates.

An initial full run used the new database before applying migrations and failed
with missing tables. Applied the existing Alembic migrations; the complete
successful run above supersedes that setup failure. Initial ty and Hypothesis
fixture-scope findings were corrected without suppressions. Existing upstream
FastAPI/Starlette deprecation warnings remain.

Next work: resolve startup ownership, implement repeat-safe configuration and
host coexistence, complete safe formatting/truncation and isolated-process
regressions, prove new installed logging imports, and finish all phase-1 gates.
The original phase-7 semantic review and exact framework dispositions remain
outstanding as documented in `python-verification.md`; logging does not replace
them. No logging PR has been opened, and no next dependent feature branch has
been started. Container/hosted mode acceptance and final release gates remain
unverified. Refresh Dev again before publication and target non-draft PRs at Dev.

## Phase 1 hardened formatter checkpoint

Continued on the same current-Dev foundation branch; refreshed remotes and
confirmed there are no failing feature pipelines. The only open PR is the
existing release-to-Prod promotion, whose required checks are green. It was
not merged or otherwise changed.

Added validated record-limit boundaries, explicit frame/chain truncation and
cycle handling, metadata validation for programmatic settings, and bounded
fallback records with the same required envelope and selected format. The byte
ceiling includes the text prefix and terminating newline. When necessary,
optional context is removed in a fixed order, with correlation identifiers last;
the remaining event, severity, timestamp and component stay valid. Diagnostics
are limited to 1–8 KiB, identifiers to 16–256 characters, frames to 1–64 and
exception chains to 1–8 entries. The defaults above remain unchanged.

Only `app`, `backend`, `ml` and `__main__` namespaces may contribute the
allowlisted application context. Dependency records use `dependency.record`
and cannot smuggle arbitrary event/context extras into output. Application
callers remain responsible for providing generated IDs and controlled source,
stage and event identifiers, rather than user input. Numeric-leading UUIDs are
retained. No original message, argument, exception text or note is interpolated.

The package gate now proves the installed API wheel includes the logging
modules and excludes logging test support, and that the isolated installed ML
environment can import the shared formatter/sink through its backend dependency.
A new fresh-process test proves silent imports, no environment/handler/level
mutation, no database URL requirement and no sqlalchemy/dotenv imports.

Final checkpoint results:

- **813 passed, zero skips**, **92.11%** aggregate coverage, **36.41 seconds**.
- API/shared-calendar coverage remains **100%**. Logging support coverage is
  **99.10%**; this does not replace the outstanding startup/lifecycle scenarios.
- Isolated units: **763 passed**, **50 integrations deselected**, **23.07 seconds**.
- **44 logging cases** cover both formats, all five severity thresholds, generated
  hostile exception text, size limits, correlation retention, safe stack
  locations, frame/chain limits, exception cycles, unsafe metadata, unknown
  objects, dependency extras, sink failures and silent imports.
- Locked sync, Ruff lint/format, ty, structural gate, dependency exports,
  OpenAPI parity, ML gate, updated isolated package installs and wheel/sdist
  exclusions passed. New-source searches found no prohibited constructs or
  added comments. Existing dependency deprecation warnings remain.

This checkpoint still does not install logging in an entrypoint or complete
phase 1. The owner approval question for the proposed API lifespan hook remains
unanswered. Repeat-safe configuration, host coexistence and supported-host
bootstrap acceptance must follow that decision before publication. No PR has
been opened and no dependent phase has started. The dedicated disposable
PostgreSQL container was removed after verification; unrelated containers were
untouched. The local historical `plan.md` remains untracked and unchanged.

## Phase 1 approved startup and local acceptance

The owner resumed work with: "resume please follow python rules and use that
hook." This explicitly approves the hosted exception described in the plan.
`create_runtime_app()` resolves logging from the existing merged environment
snapshot before HTTP/database settings. It passes immutable logging settings to
`create_app()`; only that application's lifespan startup installs handlers,
before database resource construction. Ordinary imports, OpenAPI generation,
and application construction remain free of logging installation. Command
`main()` functions will call the same shared configurator in phase 3.

One named, process-owned stderr handler serves the application namespaces.
Repeated startup with identical settings reuses it. Conflicting process settings
require a restart; an unrelated handler using the reserved name is preserved
and rejected rather than overwritten. Application propagation stops before the
host root. Root and Uvicorn loggers/handlers remain untouched. SQLAlchemy and
HTTP dependency namespaces use the safe sink at WARNING or the selected stricter
threshold, so application DEBUG does not enable parameter/URL logging. No global
mutable configuration store, background queue or forced root replacement was
introduced. Initialization belongs to the synchronous main/startup boundary,
before serving requests; this is not a per-request reconfiguration API.

Fresh-process scenarios exercise the configuration service's silent imports,
repeated configuration and Vercel-export lifespans, both thresholds/formats,
resource-construction order, host preservation, reserved-name conflicts and
changed-settings rejection. Invalid logging fails before database-setting
resolution. Additional concrete HTTPError/SQLAlchemy OperationalError scenarios
verify nested payload/parameter/header/URL exclusion and exception identity.
The existing dotenv merger retains exported-value precedence without mutation.
Environment templates and backend/deployment instructions document the contract.

Final local gates on Python 3.12.14 and the newly provisioned disposable
PostgreSQL 15 database `tradevalue_test_logging01_final`:

- **833 passed, zero skips**, **91.71%** aggregate coverage, **40.27 seconds**.
  The API/shared-calendar behavior gate remains **100%**.
- Isolated units with database URLs absent and dotenv disabled: **783 passed**,
  **50 integrations deselected**, **23.68 seconds**.
- Ruff lint/format, ty, structural rules, locked all-group sync, OpenAPI parity,
  dependency exports, ML gate, isolated API/ML installs and wheel/sdist boundaries
  passed. New-source/diff scans found no forbidden constructs or added Python
  comments. The approved startup exception is recorded explicitly, rather than
  treated as a general rule waiver.
- Frontend API contract, lint, **60 tests at 100% coverage**, and production
  build passed. The first invocation used a nonexistent `check:api` script;
  corrected to the repository's `api:contract` command. No frontend code changed.
- Production image `tradevalue-logging01:verified` built and served health,
  seasons and teams successfully in INFO and DEBUG as uid **10001**.
  Separate real-image lifespan probes captured empty stdout and one INFO event
  in normal mode, INFO plus DEBUG in debug mode, safe JSON on stderr, no raw
  sensitive message, and one application handler. Local captures are at
  `/private/tmp/tradevalue-logging01-{info,debug}-probe.{stdout,stderr}`.
- Earlier bootstrap-test fixture errors (host propagation and unrelated
  TestClient deprecation output) were corrected by matching host logger setup
  and exercising ASGI lifespan directly. No production warning suppression or
  weakened event assertions was added. Existing upstream dependency warnings
  remain in the complete suite.

Pulled current `origin/Dev` before publication; it remained `4d8fae3`. Phase 1's
local deliverables and gates are complete. Hosted PR checks and publication
follow; request/access/lifecycle instrumentation is phase 2. Vercel's documented
lifespan support establishes the bootstrap design, but shutdown output is not
retained in its dashboard and cleanup is limited to 500 ms. Hosted retention,
access, sink limits and captured-mode acceptance remain phase-5 rollout gates.
The earlier phase-7 semantic acceptance remains outstanding and is not waived.
No production promotion or manual PR merge is part of this work.

## Phase 1 publication and phase 2 start

Published exact verified phase-1 head
`64418853ecf8e2bb4466d00235007169c1c53c94` as non-draft PR
[#165](https://github.com/ecillie/hockey-analytics/pull/165), targeting `Dev`.
Dev workflow `41263896315`, both Vercel previews, and all required checks passed.
Repository automation merged it at `2026-11-01T02:10:27Z` as
`9f355daf841074a7eee403816589de048c499fe1`. No pipeline fixes or manual merge
were needed. All phase-1 verification containers were removed; the unrelated
existing container was untouched.

After confirming the merge, fetched Dev and started `feature/logging-02-api`
from `9f355da`. Its initial implementation adds a streaming ASGI correlation
component, immutable per-request context and monotonic duration, generated
response request IDs, controlled route-template fields, and final outcome
summaries. Caller/upstream request IDs are replaced. The component copies the
per-request state mapping before adding its context and keeps summary state
local to each call, without a module-level ContextVar or request registry.

Six targeted scenarios pass: immediate chunk delivery without body buffering,
original exception/cancellation identity, quiet successful health probes with
failed probes retained, and interleaved requests with independent IDs even when
input scopes share a state mapping. Concurrent test work uses an awaited
`asyncio.TaskGroup`; its `tasks.create_task` call is structured concurrency,
not a fire-and-forget task. Raw bodies, paths, query strings and caller IDs do
not enter serialized diagnostics.

This is a phase-2 checkpoint, not API acceptance. The component is not yet
installed around the application middleware stack. CORS exposure, ownership of
error diagnostics and framework propagation, startup/shutdown events, host
access/error-log coordination, complete response-path coverage, and final
container/Vercel checks remain before a phase-2 PR. The historical local
`plan.md` remains untracked and unchanged.

Phase-2 checkpoint verification: Ruff lint/format, ty and structural rules
passed. On newly provisioned PostgreSQL 15 database
`tradevalue_test_logging02_checkpoint`, the complete Python suite passed
**839 tests, zero skips**, **91.75%** aggregate coverage in **39.05 seconds**;
the API/shared-calendar gate remains **100%**. No frontend or serialized API
boundary changed at this checkpoint. Final phase-2 package, frontend, container,
and hosted acceptance gates remain pending the middleware integration above.

## Phase 2 API acceptance

The API integration now wraps the complete HTTP stack in request correlation
and CORS handling. Every application response receives a generated opaque ID;
allowed origins can read it, including on error responses. Input IDs, raw paths,
queries and bodies are excluded from diagnostics. Streaming bytes pass through
immediately. A failure after headers retains the original response status and
exception identity while its final summary records the failed outcome.

| Boundary | Diagnostic owner |
| --- | --- |
| Successful, invalid, missing and handled-error HTTP responses | Request middleware emits one final summary; successful GET/HEAD health probes are DEBUG only. |
| API database, unavailable-service and unexpected exceptions | Response handler emits one `request.failed` diagnostic; the canonical propagated Uvicorn duplicate is consumed once. Unrelated host messages remain visible. |
| Unhandled streaming failures | Uvicorn emits the correlated safe diagnostic from immutable failure metadata; middleware emits the final summary. |
| Request cancellation | Original cancellation propagates; correlated host diagnostic and summary are DEBUG. |
| Successful startup/shutdown | Lifespan protocol wrapper emits `service.ready` / `service.stopped`. |
| Failed startup/shutdown | Wrapper transports bounded validated type/frame data through ASGI failure messages; Uvicorn owns the diagnostic. Startup failure is CRITICAL, shutdown failure ERROR, pure cancellation DEBUG. |

Database environment values are snapshotted at factory construction and resolved
after logging starts, retaining precedence without exposing invalid URL values
before safe handlers are installed. A secondary disposal failure remains attached
to the original primary exception for safe diagnostics. The root host handler is
preserved; application and Uvicorn namespaces use safe stderr delivery without
propagating raw exceptions into Vercel's root IPC handler. Existing Uvicorn handler
objects are retained and access logging is disabled. Docker now uses `exec` so
SIGTERM reaches Uvicorn and runs graceful shutdown.

Formatter failure uses an encoder-independent bounded fallback. Clock failure
uses an explicit `timestamp_unavailable` marker and epoch sentinel. A broken
sink never invokes logging's raw-record error dump. Both formats preserve at
least ERROR severity, including CRITICAL when selected.

Final local verification on 2026-11-01:

- Ruff lint/format, ty, structural rules, dependency exports, OpenAPI parity,
  isolated package installs, wheel/sdist boundaries and the ML gate passed.
- Disposable PostgreSQL 15 database `tradevalue_test_logging02_final`: **888
  passed, zero skips**, **91.38%** aggregate coverage in **46.58 seconds**.
  API/shared-calendar coverage remains **100%**. The isolated unit selection
  passed **838 tests**, with 50 integration tests deselected, in **28.38 seconds**.
- Frontend contract, lint, 60 tests with 100% measured coverage and production
  build passed; no frontend implementation changed in this phase.
- Rebuilt production image `tradevalue-logging02:verified` passed actual INFO and
  DEBUG HTTP probes against disposable PostgreSQL. Each mode verified six
  correlated flows: healthy, successful data, invalid input, missing route,
  unexpected exception and interrupted streaming. Original error envelopes,
  CORS restrictions and first-chunk delivery were preserved.
- Captured logs contained 15 INFO-mode and 22 DEBUG-mode events. Each unexpected
  or streaming failure produced exactly one exception diagnostic. Records stayed
  within 8 KiB, synthetic secrets were absent, and successful health summaries
  appeared only in DEBUG. Both containers exited 0 after SIGTERM and emitted one
  readiness and one stopped event. Invalid startup URL produced one sanitized
  CRITICAL `ConfigurationError`, no readiness event, and process exit 3.
- Fresh-process Vercel entrypoint tests cover repeated lifespans, frozen runtime
  configuration, real HTTP errors and distinct correlation IDs. Host interaction
  tests cover INFO, DEBUG and CRITICAL thresholds in JSON and text formats.

Repeatable HTTP and captured-log probes are in excluded test support:

```bash
uv run python -m app.shared.observability.tests.verify_http \
  http://localhost:58001 http://localhost:58002 \
  > /private/tmp/tradevalue-logging02-probe-results.json
uv run python -m app.shared.observability.tests.verify_logs
```

Run two local containers with `app_probe:create_probe_app --factory`, mount the
observability test-support directory read-only at `/verification`, and set
`PYTHONPATH=/verification`. Use ports 58001/58002, INFO/DEBUG respectively, JSON
format and a disposable test database. Stop them before capturing `docker logs`
to `/private/tmp/tradevalue-logging02-{info,debug}.log`. Capture the invalid-URL
startup probe to `tradevalue-logging02-startup-failure.log` and its inspected exit
code to the adjacent `.exitcode` file. Probe CLI options allow artifact paths to
be changed. These fakes and probes are excluded from published packages.

Diff review found no added forbidden constructs or comments. Existing structured
concurrency uses an awaited TaskGroup. ASGI application/send awaits delegate host
protocol flow control; owned engine cleanup retains its explicit timeout.
Hosted preview checks and publication follow this record. Actual hosted capture,
retention, permissions and sink limits remain phase-5 gates; the two harmless
pre-lifespan Uvicorn status lines still use the host format. Existing phase-7
semantic acceptance remains outstanding. No production promotion is authorized
by these local results.

## Phase 2 publication and phase 3 start

Published phase-2 head `6759bff47ea120506c3f7f80b5edf0d0363e2dd7` as non-draft
[#167](https://github.com/ecillie/hockey-analytics/pull/167), targeting `Dev`.
Dev workflow `41272654327`, both Vercel previews and all required checks passed.
Automation merged it at `2026-11-01T04:23:37Z` as
`180eff469dc458efd48993c64a1fddd6a068fcd1`. No pipeline fixes or manual merge
were needed. Probe containers were removed; disposable PostgreSQL remains for
phase-3 verification and the unrelated existing container is untouched.

Started `feature/logging-03-jobs-commands` from refreshed `origin/Dev` at that
merge. Its initial checkpoint migrates OpenAPI export to shared logging settings
resolved from the explicit process environment, without adding dotenv or database
requirements. Only `main()` installs handlers, after argument validation. A frozen
invocation context carries generated identity, source and monotonic duration;
start/finish summaries and translated errors share that identity. Requested stdout,
stale-contract behavior and exit codes are preserved. Invalid logging values are
usage errors before writes, without echoing the supplied value.

Fourteen fresh-process scenarios pass across INFO/DEBUG, JSON/text, successful
export, verification failure, execution failure and invalid configuration. Existing
command contract tests retain caplog visibility through a fixture that restores
logger state and closes its owned handler after each test.

Checkpoint verification: Ruff lint/format, ty, structural rules, export/OpenAPI
parity, isolated package boundaries and ML gate passed. After applying migrations
to newly provisioned PostgreSQL database `tradevalue_test_logging03_checkpoint`,
the complete suite passed **902 tests, zero skips**, **91.71%** coverage in
**47.80 seconds**, with the API/calendar gate at **100%**. Isolated units passed
**852 tests**, with 50 integration tests deselected, in **34.68 seconds**. The first
full attempt found the new database's missing schema; it was initialized before
this successful acceptance run. No phase-3 PR is open yet. Other commands, ingestion
and worker correlation, commit-aware summaries, ML boundaries, Alembic, cancellation
and cleanup evidence remain to complete this phase.

### Phase 3 operational-command checkpoint

All seven database operational entrypoints now install the shared policy from
their `main()` after argument validation. Along with OpenAPI export, they emit
generated invocation identity, source, monotonic duration, completion outcome
and a single owned exception diagnostic. Application-aware smoke/repair commands
retain dotenv precedence; standalone verification commands use explicit process
values. Existing requested reports, transaction ownership and exit codes remain
unchanged. Preflight rejection uses controlled `unversioned_schema` or
`multiple_revisions` stage fields. Structural violations retain bounded source
module, line and rule fields without exposing absolute paths.

Forty-two fresh-process operational failure cases cover INFO, DEBUG and CRITICAL
thresholds in both formats. The harness narrowly ignores the known Starlette
httpx deprecation warning during imports; production warning behavior is unchanged
and these tests establish logging output, not the absence of pre-configuration
dependency warnings. Existing dependency warnings remain visible in full-suite
results. In-process command tests restore namespace state and close their owned
handler; this fixture now covers structural and snapshot command callers too.
The `source_module` field avoids Python LogRecord's reserved `module` name.

Final checkpoint verification on disposable migrated PostgreSQL database
`tradevalue_test_logging03_operations`: **944 tests passed, zero skips**, **91.51%**
coverage in **57.14 seconds**; API/calendar remains **100%**. Isolated units passed
**894 tests**, with 50 integration cases deselected, in **46.01 seconds**. The real
migration lifecycle passed unsafe-schema rejection, offline SQL, repeated upgrade,
schema parity, API smoke and downgrade/re-upgrade. Ruff lint/format, ty, structural
rules, dependency/OpenAPI parity, isolated packages and ML gate passed. Diff review's
only new forbidden-word hit is the assertion that the structural fixture reports
the `lambda` rule; it is test data, not executable lambda syntax.

This remains an internal phase-3 checkpoint. Ingestion/worker correlation,
commit-aware source summaries, ML boundaries, Alembic logging reconciliation and
cancellation/cleanup coverage still precede the phase-3 PR. No phase-3 publication
or release acceptance is implied by these checks.

### Phase 3 ML checkpoint

All nine supported ML commands now install the shared policy only in `main()`,
after argument validation. Application-aware commands retain dotenv/exported
precedence; the standalone metric gate uses explicit process values. Generated
invocation identity connects their command summaries and translated failures.
The former per-command `basicConfig` calls have been removed.

| Boundary | Owner and evidence |
| --- | --- |
| Standalone data/feature commands and dataset pipeline | CLI emits `ml.dataset_ready` with aggregate rows before its original requested report. Pure transformation helpers remain silent. |
| Training dataset and split preparation | Explicitly supplied context connects dataset readiness/validation and DEBUG-only `ml.split_ready` counts. No global context store is used. |
| Model fitting and split evaluation | Training orchestration emits fit boundaries and validated aggregate rows/MAE/RMSE/R2. Model options, split selection and metadata serialization are unchanged. |
| Model evaluation | Orchestration emits loaded-bundle, dataset readiness and aggregate evaluation events; no predictions or player values enter diagnostics. |
| Artifact writes | Adapter emits `ml.artifact_written` only after the corresponding model, metadata or prediction write. A later failure retains only earlier completed-write events. Artifact paths are excluded. |
| Committed metric gate | Metadata validation and each successful aggregate metric comparison are reported before the unchanged stdout success line. |
| Exceptions | CLI translation owns one `command.failed` diagnostic and a failed completion summary; library functions propagate the original failure without logging it again. |

Library entrypoints accept optional immutable invocation context. Existing callers
without it remain silent. The shared formatter allowlists only numeric aggregate
metric/count fields and includes them in its bounded truncation policy.

New behavioral tests exercise real deterministic training, artifact persistence
and evaluation in INFO/DEBUG and JSON/text. Logged and unlogged training produce
identical predictions and metadata; input frames remain unchanged. Private input
columns, player values and artifact paths are absent from diagnostics. A metadata
write failure after model persistence records only the completed model write.
Nine ML cases extend the fresh-process failure matrix across INFO, DEBUG and
CRITICAL in both formats; all retain exit 1, empty stdout and one safe diagnostic
when allowed by the selected threshold. Targeted command/ML checks passed **227
tests**. Existing help and argument-validation contract tests still pass.

Checkpoint acceptance on newly provisioned, migrated PostgreSQL database
`tradevalue_test_logging03_ml`: **1,010 tests passed, zero skips**, **91.28%**
aggregate coverage in **98.94 seconds**; API/calendar remains **100%**. Isolated
units passed **960 tests**, with 50 integration cases deselected, in **82.53
seconds**. Ruff lint/format, ty, structural rules, dependency/OpenAPI parity,
isolated package boundaries and the committed ML metric gate passed. Diff review
found no added forbidden constructs or comments. ML support remains excluded from
the API wheel; the installed ML wheel resolves its shared logging dependency.

This checkpoint does not complete phase 3. Ingestion/run/worker correlation,
retry and commit-aware summaries, Alembic logging, broader invalid-configuration
and cancellation/cleanup acceptance remain before publication. Frontend and
combined hosted/release acceptance remain later phases, as does the previously
outstanding phase-7 semantic audit.

### Phase 3 ingestion-context checkpoint

The three ingestion entrypoints now install shared logging from `main()` after
argument validation and retain application environment precedence. All 20
application command entrypoints have migrated; Alembic's framework configuration
is the remaining separate bootstrap. Fresh-process tests now cover invalid level
and format values before work across every application command, in addition to
the existing help/unknown-option and failure tests.

An immutable `IngestionContext` carries invocation, source, stage and optional
durable run identity. The tracking decorator enriches an explicitly supplied
keyword context with the allocated run ID and forwards it to services/workers.
It replaces only an existing value verified as `IngestionContext` through a local
`dict[str, object]` view of Python's per-call keyword dictionary; it does not add
parameters or alter a caller-owned context. Its public ParamSpec signature is
preserved. Unit tests prove caller immutability and boundary-controlled source,
stage and run fields. Legacy calls without context retain their existing behavior.

| Boundary | Events and ownership |
| --- | --- |
| Tracked source job | `ingestion.started` and `ingestion.finished`, with outcome, duration and available durable counters. Failed summaries carry no duplicate traceback. Cancellation summaries are DEBUG-only. |
| MoneyPuck, NHL rosters/stats and schedule | Aggregate validation events, with DEBUG row/page/worker progress; no source rows, paths or URLs. |
| Concurrent NHL jobs | Each worker receives the service's immutable run context and reports bounded season, game type and player kind. Tests interleave two services and four workers without identity leakage. |
| Historical contracts | Batch-start detail is DEBUG; committed events occur after repository context exit. Preview events explicitly report zero committed writes. A later failure reports earlier durable progress from `IngestionBatchError`. |
| Profile retry and fallback | DEBUG decisions carry attempt/status and source identity without URL, player or exception values. Batch fallback summaries are WARNINGs. Last-good snapshot retention emits a correlated WARNING after the retained snapshot is loaded. |
| Active contracts and roster status | Aggregate snapshot/feed progress travels with the run context. The owning transaction and tracker still control persistence; classification is separate from commit success. |
| Ingestion runner cleanup | Shared cleanup preserves the original exception/cancellation if session close also fails; a close failure after otherwise successful work still propagates. |

Completed-record counts come from the existing `records_created` and
`records_updated` counters, not guessed player/team dimensions. The formatter
allowlists and bounds the added game-type, player-kind and failure-count fields.

Real PostgreSQL tests show that a second historical batch failure leaves the
first 100 contracts/200 contract seasons committed and emits exactly one completed
batch event with 300 committed records. The failed run summary agrees with stored
run accounting. Resumption allocates a distinct run ID and completes. Preview
tests emit two zero-write preview events and leave contracts, snapshots and run
tracking untouched. Retry tests run through a worker thread, preserve responses
and delays, and exclude synthetic URL/payload secrets in both formats and modes.
Cancellation, secondary reporting failure and partial-progress tests preserve
original exception identity without library-owned duplicate error diagnostics.

Final checkpoint on newly provisioned and migrated PostgreSQL database
`tradevalue_test_logging03_ingestion`: **1,101 tests passed, zero skips**,
**91.38%** aggregate coverage in **124.14 seconds**; API/calendar remains **100%**.
Isolated units passed **1,051 tests**, with 50 integration cases deselected, in
**107.81 seconds**. Ruff lint/format, ty, structural rules, dependency/OpenAPI
parity, installed package boundaries and the ML gate passed. Diff review found
no new forbidden constructs or comments. Historical `plan.md` remains untouched.

This is an unpublished checkpoint, not completed phase-3 acceptance. Remaining
work includes transaction outcome/rollback diagnostics, failures in durable-status
reporting after completed work, command cancellation and secondary cleanup
diagnostics, Alembic reconciliation, and final phase/container/CI checks. Alembic
currently retains its old `fileConfig`; its CLI also has framework-owned error
rendering outside the environment callback, which must be accounted for rather
than assuming a handler change alone sanitizes that path. No phase-3 PR or release
completion is claimed. Frontend, hosted capture and the phase-7 semantic audit
remain later acceptance work.

### Phase 3 transaction and command-lifecycle checkpoint

Transaction observation now occurs in the DB-API owner immediately after commit
or rollback returns, with an explicit rollback-failed outcome when needed. A
minimal runtime-checkable context protocol keeps the serving database module
independent of ingestion packages. Frozen factories carry context into default
source, active-contract and historical-contract repositories and roster status
transactions. Injected factories keep their own ownership. Transaction events do
not claim row writes: a committed transaction can be read-only, and rollback row
counts are omitted when they are unknown.

The shared cleanup helper preserves existing notes and retains the first cleanup
exception as safe metadata. Additional cleanup detail is marked truncated rather
than silently discarded or serialized through unrestricted note text. A separate
flag preserves the distinction between repeated cancellation and genuine cleanup
failure even when diagnostics are truncated. The API lifespan adapter uses the
same retention behavior. Original exception identity, cause and cleanup ordering
remain unchanged in resource tests.

Every application command now installs a frozen process-owned exception hook
from its `main()`, after logging setup and invocation creation. This hook handles
only exceptions that reach the interpreter; ordinary handled failures still use
their existing translation path. It emits one safe diagnostic and completion
summary, while allowing cancellation to propagate normally. Pure cancellation is
DEBUG-only; additional cleanup/status failures remain ERROR. Library functions
do not log a traceback and re-raise it. API bootstrap and ordinary imports do not
install this command hook, and in-process tests restore the original hook.

Fresh-process tests cover task cancellation, keyboard interruption, cancellation
plus a genuine cleanup failure, and repeated cleanup cancellations in INFO/DEBUG
and JSON/text. No raw exception values reach stderr. CPython preserves task
cancellation status 1 and SIGINT termination (subprocess `-SIGINT`, shell 130).
Bounded multiple-cleanup diagnostics are explicitly truncated. Tracking tests
also prove that a failed durable-status update retains known completed work
counts rather than dropping them from the failed run summary.

Transaction fault tests cover successful commit, work failure, commit failure,
rollback failure, expected cancellation and close failure after commit, preserving
original identity and reporting only actual outcomes. Real PostgreSQL tests verify
committed and rolled-back data against their events. Existing historical-batch,
ingestion, resource and API lifecycle checks still pass.

Final checkpoint on newly provisioned, migrated PostgreSQL database
`tradevalue_test_logging03_transactions`: **1,159 passed, zero skips**, **91.41%**
aggregate coverage in **130.17 seconds**; API/calendar remains **100%**. Isolated
units passed **1,109 tests**, with 50 integration cases deselected, in **113.14
seconds**. Ruff lint/format, ty, structural rules, dependency/OpenAPI parity,
isolated package installs/boundaries and the ML gate passed. Diff review found
no added forbidden constructs or comments.

Phase 3 remains unpublished. Alembic framework reconciliation and final combined
phase/container/CI acceptance remain before the PR. Its existing bootstrap must
account for framework-caught CommandError output as well as uncaught failures;
changing handlers alone does not cover both paths. Frontend, hosted rollout and
the outstanding phase-7 semantic audit remain later acceptance requirements.

## Phase 3 local acceptance

Alembic now delegates its environment callback to repository-owned runtime
composition. `main()` validates shared settings before resources, preserves root
handlers, and replaces `fileConfig` without disabling unrelated loggers. CLI
execution failures are translated once before Alembic's outer handler can print
raw values. Framework errors retain status 255, `--raiseerr` retains 1, and SQL
stdout remains separate. Programmatic callers retain original exception identity,
root handlers and exception hook. Pre-callback native help/configuration messages
retain framework output. Revision steps are DEBUG `rendered` or `pending` events,
never claims of a commit before the framework transaction exits. Frozen revision
metadata/SQL remain unchanged. The environment callback must return on success
so Alembic can finish its own command; only a translated CLI failure exits there.

Thirty fresh-process Alembic cases cover both formats/modes, offline SQL, connection
failure, revision errors, raiseerr, invalid logging settings and programmatic
ownership. The real migration round trip, repeated upgrade, schema parity and API
smoke pass. Controlled failure stages retain actionable configuration reasons
without arbitrary exception messages or database paths.

Final audit also added HTTP-adapter recovery observation: native requests/urllib3
retry history produces only a correlated attempt count, without changing retry
budgets, statuses, delays, payloads or error propagation. Unknown response/history
objects are ignored. Sixteen native-response behavioral cases cover JSON/CSV,
first success and recovered success, both formats and modes. Contract/active
profile boundaries also observe native adapter recovery. The complete implemented
Python event/entrypoint inventory is [Logging event owners](logging-events.md).

Combined acceptance on 2026-11-01:

- Locked all-group sync, Ruff lint/format, ty, structural rules, dependency exports,
  OpenAPI/generated-type parity, isolated packages and ML gate passed.
- Newly provisioned/migrated PostgreSQL database `tradevalue_test_logging03_final`:
  **1,205 passed, zero skips**, **90.58%** aggregate coverage in **162.90 seconds**.
  API/calendar remains **100%**. Isolated units passed **1,155 tests**, with 50
  integration tests deselected, in **140.41 seconds**.
- Frontend checks passed under **Node 24.22.2**: contract, lint, **60 tests** with
  **100%** measured statements/branches/functions/lines in **7.63 seconds**, and
  production build. The initial shell selected Node 23; that run was superseded
  by the supported-Node run. No frontend implementation or dependency lock changed.
- Rebuilt production image `tradevalue-logging03:verified` ran as UID 10001 against
  independent disposable database `tradevalue_test_logging03_probe`. INFO/DEBUG
  probes each passed six HTTP/streaming flows and captured-log verification:
  **15 / 22 events**, correlated IDs/CORS, unchanged bodies/statuses, one exception
  diagnostic per unexpected/streaming failure, bounded records, no synthetic
  secrets and healthy-probe suppression at INFO. Both exited **0** after graceful
  shutdown. Invalid startup produced sanitized CRITICAL diagnostics and exit **3**.
- Captures are under `/private/tmp/tradevalue-logging03-capture`; the reused probe
  verifier retains its phase-2 artifact basenames within this separate directory.
  Frontend, Python, package and image transcripts use the `tradevalue-logging03-`
  prefix in `/private/tmp`. Existing earlier-phase evidence was not overwritten.
- Manual branch-diff review confirms frozen values, main-owned command setup,
  lazy diagnostic arguments, explicit context propagation, resource cleanup,
  phase-specific error ownership and role-file separation. CLI translation logs
  and returns; the programmatic Alembic branch raises without an error diagnostic.
  No new forbidden constructs/comments were found; the sole `lambda` search hit
  is the structural-verifier fixture assertion. Historical `plan.md` is untouched.

Phase-3 local deliverables and acceptance gates are complete. Publication and
required hosted checks follow. This does not complete logging phase 4/5, hosted
capture/retention/access/limits acceptance, or the existing phase-7 semantic audit.
No production promotion or manual PR merge is part of this acceptance.

## Phase 3 publication and phase 4 start

Published verified head `3453a6c10ff2a3f3a588e0c739a6bf97105299b8` as non-draft
[#169](https://github.com/ecillie/hockey-analytics/pull/169), targeting `Dev`.
Dev workflow `41277244180`, both Vercel previews and all required checks passed.
Automation merged it at `2026-11-01T05:37:00Z` as
`0d1aaa2889e193b165082af24d7104be522b6570`. No CI fixes or manual merge were
needed. Probe containers were removed; disposable PostgreSQL remains available
for following local verification, and the unrelated existing container is intact.

Started `feature/logging-04-frontend` from freshly fetched `origin/Dev` at that
merge. Its first checkpoint adds the shared pure browser threshold parser and
severity policy. Missing settings default to INFO; all five standard levels accept
case/whitespace normalization, and empty/unknown values fail without echoing the
input. Vite validates `VITE_LOG_LEVEL` through that same parser while loading its
configuration. The Node TypeScript project explicitly includes this shared source
module; coverage inclusion/exclusions and thresholds remain unchanged.

Under Node 24.22.2, contract validation, lint, **76 tests at 100% measured coverage**,
and production build pass. A real build with an invalid synthetic value fails
with only controlled choices. A normalized DEBUG build with the live API selector
also passes. An initial combined validation accidentally applied live-API mode to
route tests that require mock data; the successful final run uses mock mode for
tests and switches only the build to live-API mode. Neither source behavior nor
test expectations were changed to accommodate that environment mistake.

This is an unpublished phase-4 checkpoint. Runtime console delivery, bounded safe
fields, server request-ID correlation, API failure ownership, global listeners,
render fallback and associated behavior tests remain. React root error callbacks
must join that ownership model to prevent raw default console reports; the
[React createRoot reference](https://react.dev/reference/react-dom/client/createRoot)
and installed React DOM types confirm caught, uncaught and recoverable callbacks.
The React best-practices skill is being used for initialization/listener and
component review. No frontend logging or phase-4 acceptance is claimed yet.
The dedicated checkpoint PostgreSQL container was removed after verification.

## Phase 4 local acceptance

Completed the browser implementation on `feature/logging-04-frontend`, based on
Dev merge `0d1aaa2889e193b165082af24d7104be522b6570`. The logger owns finite
per-severity counters and weak object-error deduplication. It emits primitive
allowlisted JSON fields only, with independent fallback formatting and contained
sink/clock faults. The API client owns request failures, retains existing error
fields and abort/decode identities, and adds a validated server request ID.
Page-level retry remains unchanged. Root callbacks own React diagnostics and
replace default raw console reporting. The boundary renders a generic accessible
fallback, and bootstrap owns global listeners outside StrictMode effects, with
cleanup for hot replacement. Imports remain silent until explicit activation.

Local verification on 2026-11-01 under Node **24.22.2**:

- `npm run lint`, `npm run test:coverage`, `npm run api:contract` and live-API
  `npm run build` passed. **163 tests** passed in **7.22 seconds**, with **100%**
  statements, branches, functions and lines across measured shipped modules.
  New helpers and the error boundary remain measured; no thresholds or exclusions
  changed. Tests cover all severities, bad settings/fields, missing or malformed
  IDs, HTTP/network/decode/response failures, aborts, listener ownership, root
  callbacks, StrictMode deduplication, formatter/sink/clock faults and rate windows.
- Separate production INFO and DEBUG artifacts were built with the live API
  selector against an isolated HTTP contract harness, then exercised in headless
  installed Google Chrome using a temporary Playwright harness. Both modes
  rendered the overview, preserved HTTP error/retry UI, correlated the server's
  exact request ID, cancelled navigation requests quietly, deduplicated an error
  shared by global error/rejection handlers, displayed the render fallback, and
  recovered through its reload link. No uncaught page errors or synthetic secret
  strings appeared in captured console output.
- Browser captures contain **29 INFO / 54 DEBUG** application records across the
  complete multi-navigation flow. Normal successes/cancellation were silent at
  INFO; DEBUG included request lifecycle records. Each new logger's 30-error loop
  produced exactly **20 error records plus one suppression notice**. Every record
  stayed below 8 KiB. The fixture's initial scalar season list was corrected to
  the actual contract shape before final verification; no application behavior
  changed to accommodate it. Final overview and fallback screenshots were
  inspected. Captures, screenshots and the temporary harness are under
  `/private/tmp/tradevalue-browser-probe`; the complete final command transcript is
  `/private/tmp/tradevalue-logging04-browser-final.txt`.
- Manual React checklist review confirmed initialization outside effects, one
  owned subscription, cleanup, stable error ownership, accessible fallback, no
  extra fetching or dependencies and no changes to existing hooks. Contract and
  lock files are unchanged. `git diff --check` passed. Python files were unchanged
  in this phase; combined Python/package/image acceptance belongs to phase 5.

Environment examples, README, deployment guidance and the event inventory now
describe console-only browser scope, five severities, safe request correlation,
limits, DEBUG rebuild and restoration to INFO. Browser-local capture does not
prove hosted API capture, retention, access or platform limits. Those checks and
the complete phase-7 semantic audit remain required before release completion.
Historical untracked `plan.md` remains untouched. Phase 4 is ready for a non-draft
PR targeting Dev; no deployment or manual merge is performed by this record.

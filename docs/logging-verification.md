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

## Phase 4 merge and phase 5 hosted dependency checkpoint

Non-draft [PR #171](https://github.com/ecillie/hockey-analytics/pull/171), head
`d67bc3fefe1b2401741462409485e92f1660dd0d`, passed Dev workflow `41278993774`,
frontend checks and both Vercel preview builds. Automation merged it at
`2026-11-01T06:00:38Z` as `23dcfb2e2fd865750823b6372afa059c118baff3`.
Started `feature/logging-05-acceptance` from freshly fetched origin/Dev at that
merge. No manual merge or CI repair was needed for phase 4.

Read-only Vercel dashboard inspection found a hosted runtime failure despite the
green backend preview build. Deployment `dpl_7T8tHgDrXzeDUEBvrGmLwwZvhgFY`, source
`d67bc3f`, was Ready, but Runtime Logs recorded cold-start installation failures
at `2026-11-01T06:00:34Z` and `06:00:36Z`. The platform's deferred uv sync used the
parent workspace lock and could not find `file:///var/task/_uv/backend`. The
application did not start, so these platform failures prove neither application
logging nor application severity behavior. The connector returned no teams;
existing authenticated browser access provided the dashboard evidence. No
permissions, credentials or protection settings were changed.

The backend configuration now explicitly installs generated API requirements
with `uv pip install --no-sources -r requirements.txt` in the build virtualenv.
The backend distribution is built normally; no repository dependency versions,
lock, environment selectors or runtime source paths change. Vercel's builder
source shows custom installation uses a fresh virtualenv and bundles dependencies
instead of deferring this workspace lock to cold start. Actual hosted validation
of the fix remains pending; do not infer success from source inspection alone.

The strengthened package gate runs the configured install command with the
parent workspace present, then imports the result outside the checkout. It
passed with 20 API packages, the installed 18-path API and shared logger, no
editable source dependency, and no ML, ingestion or test packages. Both wheel/
sdist and existing API/ML isolated installs and ML metric gate passed. A first
test-only installed-path assertion compared macOS `/var` with `/private/var`;
resolving both paths corrected that assertion. Final transcript:
`/private/tmp/tradevalue-logging05-packages.txt`. Full combined checks have started
against new disposable database `tradevalue_test_logging05_candidate`; their
results and the final semantic audit remain pending.

## Phase 5 combined gates and hosted configuration boundary

Published dependency-fix checkpoint `80bde1a692f0c9d3a168281440c6cae8c3869e6e`
on the acceptance branch without opening a PR. Its automatic backend preview is
`dpl_31FEto4YJHcMtWbfiqdeqeZd6TWc`. The build passed in 12 seconds; invoking
`/docs` still returned platform `FUNCTION_INVOCATION_FAILED`. Runtime Logs now
contain application `service.startup_failed` CRITICAL JSON, safe type/frame-only
ConfigurationError/ValueError chains, matching release metadata and a sanitized
Uvicorn dependency record. The missing workspace distribution failure is gone.
The later platform `vc_handler` import error follows the failed application
startup; it is not evidence that the dependency fix alone completes runtime
acceptance. No successful hosted request or DEBUG acceptance is claimed.

Read-only project settings explain the remaining startup failure: `ENV` exists
only in Production; only `PROD_DATABASE_URL` appears for Production and Preview.
No database values were revealed. An approved NonProd target or branch-scoped
`ENV=nonprod` and `NONPROD_DATABASE_URL` has been requested. Those dependent hosted
checks remain pending; no production secret, permission or selector was changed.
The dashboard identifies a Hobby plan, authenticated log access is available to
`ecillie`, and observed startup entries were bucketed as Info despite correct
application ERROR/CRITICAL fields. The runbook records this limitation and the
current primary-source retention and sink policies without claiming a paid drain,
extended retention, complete role audit or measured limit exhaustion.

Completed local combined gates on Python **3.12.14**, 2026-11-01:

- Locked all-group sync, Ruff lint/format, ty, structural rules, dependency
  exports, OpenAPI, linear migrations, preflight, fresh schema migration/snapshot
  and API smoke all passed.
- Fresh database `tradevalue_test_logging05_candidate`: **1,205 passed, zero
  skips**, **90.58%** aggregate coverage in **132.78 seconds**. The service/API/
  calendar selection remains **100%**. Isolated units passed **1,155**, with 50
  integration tests deselected, in **110.95 seconds**. The committed ML gate and
  all API/ML/Vercel clean-install package checks passed.
- Rebuilt production image `tradevalue-logging05:verified` ran as UID 10001
  against separate fresh database `tradevalue_test_logging05_probe`. INFO/JSON
  and DEBUG/text each passed six real HTTP/streaming flows, captured **15 / 22**
  events, exact request-ID/CORS/body/status checks, single unexpected/streaming
  error ownership, bounded safe records and graceful exit **0**. Invalid startup
  produced one sanitized CRITICAL event and exit **3**. Probe containers were
  removed; both pre-existing PostgreSQL containers remain intact.

Transcripts use `/private/tmp/tradevalue-logging05-` prefixes; image captures are
under `/private/tmp/tradevalue-logging05-capture` with the reused verifier's
phase-2 basenames inside that separate directory. The complete command scripts
are `/private/tmp/tradevalue-logging05-checks.sh` and
`/private/tmp/tradevalue-logging05-image-checks.sh`.
Frontend phase-4 evidence still applies: no frontend changes were made after its
verified and merged head. The final full semantic review is tracked file by file
in [Python semantic audit checkpoint](python-semantic-audit.md), which currently
records 18 empty modules, 20 docstring-only packages and 29 other inspected
sources. It explicitly retains unresolved dispositions and all other files as
pending. ML content inspection identified remaining role-layout, repeated
metric-map types and duplicated position-group mapping decisions to resolve.
These passing
gates do not substitute for that review or the remaining hosted checks. Phase 5
and release acceptance remain incomplete; the existing release-to-Prod PR stays
under normal checks and manual approval.

## Phase 5 ML role and ownership checkpoint

Resolved the three recorded ML review findings on the acceptance branch based
on `e78db6b`: domain.py now owns frozen options, identifiers, feature-order values
and artifact paths; repository.py adapters own SQL/artifact/metadata persistence;
services.py owns dataframe/training/evaluation orchestration; util.py owns pure
calculations and boundary helpers. Existing CLI modules retain parsing, stdout
reports, main-owned logging and explicit compatibility exports. Published command
paths, feature lists, model defaults, metadata, reports and artifact names remain
available. No dependency versions or locks changed.

One MetricValues alias retains the public string-key metric API, with enums
controlling internal metric traversal. Both dataset paths now use one controlled
position-group mapping. Unknown/null/case-mismatched codes remain null, generic
forward codes remain supported, and input/index ownership is tested. A minimal
runtime-checkable ModelDataReader permits an injected reader without resource
acquisition; its frozen SQL implementation borrows a connection. The default
context factory owns one engine/connection for missing inputs. Preloaded inputs
cause no reads, and a falsy reader is not replaced. Test arrays are constructed
in fixtures and class column metadata is immutable.

Final verification on 2026-11-01, Python **3.12.14**:

- Locked sync, Ruff lint/format, ty, structural gate, exports, OpenAPI, linear
  migrations, preflight, fresh migration/schema snapshot/API smoke and committed
  ML gate passed.
- Fresh `tradevalue_test_logging05_roles_final`: **1,208 passed, zero skips**,
  **90.74%** aggregate coverage in **129.67 seconds**; the API/calendar selection
  remains **100%**. Isolated units passed **1,158**, with 50 integrations
  deselected, in **110.27 seconds**.
- Clean API, Vercel-install and ML wheel/sdist checks passed, including installed
  legacy entrypoints and the committed model gate. Source comparison against
  pinned pre-refactor `e78db6b` confirms **22 moved function bodies**, **nine CLI
  main/parser bodies**, original argparse metadata and both SQL literals are
  unchanged. Dataset connection ownership and shared grouping changes have
  separate behavioral regressions.
- Focused ML/CLI/entrypoint checks passed **295 tests** before the final complete
  run. The initial complete role run passed 1,208/1,158 as well; final runs above
  supersede it after fixture corrections and restoration of original help
  metadata. An early module-docstring placement error and missing compatibility
  exports were corrected before final checks. Review also removed copied CLI
  definitions from the evaluation service; passing tests alone were insufficient
  to detect that layout mistake.
- `git diff --check` and prohibited-form searches passed. No Python comments,
  dependency/environment changes or frontend edits were added. The backend and
  frontend trees are unchanged in this checkpoint, so their prior built-image
  and Chrome evidence still applies; ML's changed artifacts were rebuilt and
  tested in fresh installations.

Final transcripts use `/private/tmp/tradevalue-logging05-roles-final-` prefixes;
the complete gate script is `tradevalue-logging05-roles-final-checks.sh` there.
The pinned source comparison script is
`/private/tmp/tradevalue-logging05-verify-moves.py`. The strengthened audit ledger
now includes **237** tracked/new Python sources: 18 empty modules, 20 docstring-only
packages and 56 other inspected sources. **143** nonempty files remain pending.
Operational/shared review identified two further required fixes: caught HTTPError
response ownership in container smoke, and cleanup-note rendering that can mask
the original failure. Those findings, exact framework dispositions, hosted
NonProd success/correlation/mode checks and final release acceptance remain open.
No acceptance PR is opened until the required work is complete. Historical
untracked `plan.md` is unchanged.

## Phase 5 cleanup failure and HTTP response ownership checkpoint

Fixed both concrete findings from the ML/operational source audit, based on
acceptance head `4727840`. Cleanup-note rendering and attachment are now
best-effort operations, separate from bounded secondary-error metadata. A hostile
repr, overridden add_note or invalid native notes collection cannot replace a
pending primary error or stop later cleanup. Ordinary note text is retained.
The narrow BaseException guards protect annotation only: resource owners still
propagate the original cancellation/interrupt or first failure, and a cleanup
failure with no pending primary still propagates unchanged. No handler logs and
rethrows the same error.

The container smoke adapter now explicitly closes caught HTTPError responses.
Read/decode failure remains primary when close also fails; the shared cleanup
helper retains the secondary close failure. A close-only failure propagates.
Handled status/raw-text behavior, invalid-byte replacement and native successful
response contexts remain unchanged. Fixtures use native HTTPError/BytesIO objects
and close their buffers even when simulating failed close operations.

Regression-first evidence: **26 failed, 21 passed** before the production fixes.
The final isolated focused selection passed **80 tests**, with its two integration
cases explicitly deselected. An initial focused invocation without a database
skipped those two cases; the complete database-backed run below supersedes it.
The new cases exercise ordinary errors, cancellation and interrupts; repr/note
faults; read/close fault combinations; original identity/cause; cleanup order;
both diagnostic formats; secret omission and bounded secondary retention.

Final acceptance for this checkpoint on 2026-11-01, Python **3.12.14**:

- Locked sync, Ruff lint/format, ty, structural rules, dependency exports,
  OpenAPI, linear migration checks, preflight, fresh migration/schema snapshot
  and API smoke passed.
- Fresh database `tradevalue_test_logging05_cleanup_final`: **1,236 passed, zero
  skips**, **90.84%** aggregate coverage in **131.33 seconds**. API/calendar stays
  **100%**. Isolated units passed **1,186**, with 50 integrations deselected,
  in **110.53 seconds**.
- Clean API/Vercel-install/ML package, wheel/sdist and committed-model gates
  passed. No dependency, model artifact, schema, frontend or environment
  selection changed. Diff checks and prohibited-form searches passed; the
  existing S310 suppression retains its stated reason, and no new comments or
  suppressions were introduced.
- Rebuilt `tradevalue-logging05-cleanup:verified` ran as UID 10001 against fresh
  `tradevalue_test_logging05_cleanup_probe`. INFO/JSON and DEBUG/text each passed
  six real HTTP/streaming flows, exact ID/CORS/body/status assertions and bounded
  safe single-error diagnostics, with **15 / 22** captured events and graceful
  exit **0**. Invalid startup produced CRITICAL and exit **3**. Probe containers
  were removed; both earlier PostgreSQL containers remain intact.

Full transcripts use `/private/tmp/tradevalue-logging05-cleanup-final-` prefixes.
Image transcripts use `tradevalue-logging05-cleanup-image`; captures are under
`/private/tmp/tradevalue-logging05-cleanup-capture` with reused phase-2 verifier
basenames. Complete scripts are
`/private/tmp/tradevalue-logging05-cleanup-final-checks.sh` and
`/private/tmp/tradevalue-logging05-cleanup-image-checks.sh`.

Further content review now covers every API source file and database resource
factory. The ledger records 237 files: 18 empty, 20 docstring-only, 69 other
inspected, and **130** nonempty files still pending. The existing PlayerQuery
should move across the route/service boundary rather than being created after
ten positional arguments. Response-model mutability and summary-query option
grouping also need final boundary-specific disposition. Exact framework and
historical-migration decisions, hosted NonProd success/mode/correlation evidence
and final release acceptance remain open. No acceptance PR or production action
is implied by this verified checkpoint.

### Phase 5 API query boundary and continuing source audit

After `73c716e`, the validated players route constructs the existing frozen
PlayerQuery once and passes it through the service and repository. This removes
the long positional reconstruction while retaining the HTTP names, defaults,
validation and pagination response. SummarySelection now groups summary SQL
options and immutable binding pairs; only an execution-local dictionary is
mutable. Sort/filter SQL fragments remain code-controlled and values stay bound.
Existing filtering, traded-player aggregation, pagination/tie/null ordering and
injection regressions now receive query values from fixtures.

Verification under Python 3.12.14:

- Fresh migrated `tradevalue_test_logging05_query_final`: **1,236 passed, zero
  skips**, **90.85%** aggregate coverage in **132.03 seconds**. API/calendar
  coverage remains **100%**. Isolated units passed **1,186**, with 50 integrations
  deselected, in **110.77 seconds**.
- Locked sync, Ruff lint/format, ty, structural gate, dependency exports, OpenAPI
  parity, migration preflight/history/schema snapshot, API smoke, clean installed
  API/Vercel/ML packages, wheel/sdist exclusions and committed-model gate pass.
- Rebuilt `tradevalue-logging05-query:verified` passes INFO/JSON and DEBUG/text as
  UID 10001 against fresh `tradevalue_test_logging05_query_probe_final`. Each mode
  passes six real HTTP/streaming flows with exact IDs, CORS, bodies and statuses;
  captured events are **15 / 22**, graceful exit is **0**, and invalid startup
  produces CRITICAL with exit **3**. Probe containers are removed. An initial
  build used the wrong context and failed; the successful rebuild uses `backend`
  as required by the existing Dockerfile.
- Diff whitespace and prohibited-form searches pass. No new suppressions,
  dependencies, public schema, frontend or model artifacts changed.

Complete transcripts use `/private/tmp/tradevalue-logging05-query-final-` and
`/private/tmp/tradevalue-logging05-query-packages.txt`. Image transcripts use
`tradevalue-logging05-query-image`; captures are in
`/private/tmp/tradevalue-logging05-query-capture`, with the verifier's reused
phase-2 basenames. Scripts are
`/private/tmp/tradevalue-logging05-query-final-checks.sh` and
`/private/tmp/tradevalue-logging05-query-image-final-checks.sh`.

The semantic ledger now records 237 files: 18 empty, 20 docstring-only, **94**
other inspected, and **105** nonempty files pending. Reviewed content is not
blanket acceptance. Newly recorded findings include contract coverage numeric
truthiness, duplicated worker limits and remaining role-file/narrow-type
judgments; mutable items inside DiagnosticCollection and hostile metadata
primary-error behavior also require resolution. Native Pydantic boundary graphs
remain newly owned validation/serialization buffers, with immutable domain
snapshots across layers. Framework/historical dispositions, hosted NonProd
success/mode/correlation checks and final release acceptance remain open. No
acceptance PR or production promotion is implied by this checkpoint.

### Phase 5 immutable diagnostic snapshots and shared worker limits

After `7e45802`, DiagnosticCollection retains the existing frozen StackFrame and
ExceptionSnapshot models with tuple nesting. Dictionaries are created only by
explicit serialization. Tests reject field mutation and show that modifying a
serialized graph cannot alter the retained snapshot. Lifecycle reports consume
those same models without changing their wire shape.

Best-effort exception dictionary access and request annotation now contain faults
from metadata itself, including cancellation/interrupt, while the original
application failure propagates unchanged. These broader catches wrap only that
metadata boundary; application work, native cancellation/interrupt and stream
sink ownership remain unchanged. Request, lifespan, formatter and native host
filter regressions verify bounded secret-free diagnostics. Unreadable optional
metadata is discarded and marked truncated; a host record cannot recover the
correlation fields that could not be attached, while the request summary still
retains its request-local ID. The excluded MetadataAccessError test double must
raise at native attribute access to reproduce the failure; returning a policy
violation would not simulate that contract.

One WorkerLimitPolicy now controls validation and fetch execution. The historical
service passes its injected limits through to the fetcher. A regression exercises
an accepted nondefault limit, all concurrent session closures, and rejected direct
worker counts before session creation. ContractOptionError has its canonical
errors module with the options import preserved. Zero-row coverage handling is
explicit and keeps the previous None result.

Verification under Python 3.12.14:

- Before fixes, snapshot/metadata regressions produced **8 failures, 3 passes**;
  the custom worker-limit regression separately failed after acceptance by the
  service. Focused post-fix units passed **167** before five additional direct
  worker/host-boundary cases were included in complete acceptance.
- Fresh migrated `tradevalue_test_logging05_snapshots_final`: **1,253 passed,
  zero skips**, **91.00%** aggregate coverage in **132.28 seconds**, and **100%**
  API/calendar coverage. Isolated units passed **1,203**, with 50 integrations
  deselected, in **111.06 seconds**.
- Locked sync, Ruff lint/format, ty, structural scope, requirements exports,
  OpenAPI parity, migration history/preflight/schema snapshot, API smoke, clean
  API/Vercel/ML packages, wheel/sdist exclusions and committed-model gates pass.
- Rebuilt `tradevalue-logging05-snapshots:verified` runs as UID 10001 against
  fresh `tradevalue_test_logging05_snapshots_probe`. INFO/JSON and DEBUG/text each
  pass six HTTP/streaming flows with exact ID/CORS/body/status checks, **15 / 22**
  captured events and graceful exit **0**. Invalid startup produces CRITICAL
  and exit **3**. HTTP probe containers are removed.
- Diff whitespace and prohibited-form searches pass; no new comments,
  suppressions, dependencies, public schemas, frontend or model artifacts changed.

Transcripts use `/private/tmp/tradevalue-logging05-snapshots-` prefixes. Complete
scripts are `tradevalue-logging05-snapshots-final-checks.sh` and
`tradevalue-logging05-snapshots-image-checks.sh` under `/private/tmp`; image
captures use `tradevalue-logging05-snapshots-capture` with phase-2 verifier
basenames. Red regressions are `tradevalue-logging05-snapshots-red.txt` and
`tradevalue-logging05-worker-red.txt`.

The source ledger now records 237 files: 18 empty, 20 docstring-only, **109**
other inspected and **90** nonempty files pending. Reviewed findings remain
explicit: raw schedule-game dictionaries inside a frozen boundary model, CSV
file I/O in a pure utility role, boolean count acceptance, stat-kind narrowing,
legacy role placement and exact framework/historical dispositions. The installed
native HTTP retry adapter also has its own six-hour Retry-After maximum; the
socket timeout is not an overall retry deadline. No new transport timeout
contract is assumed. Hosted NonProd success/mode/correlation evidence and final
release acceptance remain open; this checkpoint opens no acceptance PR and
performs no production promotion.

### Phase 5 source snapshot, count and stat-kind boundaries

After `02d161a`, ScheduleDay reuses the existing immutable JSON-string snapshot
boundary instead of retaining nested mutable game dictionaries. Input aliases
cannot mutate validated rows; each games access returns a detached graph. Native
JSON/model serialization retains the original `games` shape, and nonregular
games still filter before strict game validation. A malformed nonregular row
therefore remains ignored rather than invalidating the requested regular-season
snapshot.

Durable run counts now follow the existing inferred-count rule: nonnegative plain
integers are valid; booleans, negative values and other invalid types use the
supplied fallback. The internal stat equation policy takes PlayerKind; the legacy
string boundary converts valid strings and raises PlayerKindViolation with the
native cause for unsupported kinds. Previously an unknown string silently took
the goalie branch. CSV opening moved from pure util to the source repository
adapter; its sole actual caller now imports it there. AST comparison against
`02d161a` proves the reader's complete signature/body, BOM handling, newline
settings and native file context are unchanged. No unused compatibility wrapper
was added; the remediation plan calls for wrappers only for actual callers.

Verification under Python 3.12.14:

- Before fixes, source snapshot/count regressions produced **5 failures, 8
  passes**. Unsupported-kind regressions separately produced **3 failures**.
  Focused final source units passed **76**, with 16 integrations deselected.
- Fresh migrated `tradevalue_test_logging05_source_final`: **1,269 passed, zero
  skips**, **91.01%** aggregate coverage in **129.88 seconds**, with **100%**
  API/calendar coverage. Isolated units passed **1,219**, with 50 integrations
  deselected, in **110.81 seconds**.
- Locked sync, Ruff lint/format, ty, structural scope, requirements exports,
  OpenAPI parity, migration history/preflight/schema snapshot, API smoke, clean
  installed API/Vercel/ML artifacts, exclusions and committed-model gates pass.
- Distributed API/core/shared logging code, Docker/build/dependency inputs and
  frontend source have no changes against `02d161a`. Backend artifact rules
  explicitly exclude ScriptingFiles and test support, and fresh package checks
  verify those exclusions. The already verified snapshots image's two-mode
  HTTP/streaming/startup/shutdown evidence remains applicable to those unchanged
  runtime contents; no new image or frontend build is claimed for this source-only
  checkpoint. Final combined acceptance still requires its final candidate build.
- Diff whitespace and prohibited-form searches pass. No new comments,
  suppressions, dependencies, frontend, public HTTP schema or model artifacts
  changed.

Transcripts use `/private/tmp/tradevalue-logging05-source-` prefixes. The complete
script is `/private/tmp/tradevalue-logging05-source-final-checks.sh`; the source
move comparison is `tradevalue-logging05-source-move-check.py`. Red kind evidence
is `tradevalue-logging05-kind-red.txt`.

The ledger now records 237 files: 18 empty, 20 docstring-only, **132** other
inspected and **67** test/support files pending. All supported runtime sources
have received content review; their findings still require resolution. Newly
recorded work includes failure-preserving cursor ownership in team-stint and
cached-summary readers, caught roster HTTPError response closure, transport I/O
in roster util.fetch_validated, immutable roster classification evidence and
remaining typed-validator/role dispositions. Framework/historical decisions,
hosted NonProd success/mode/correlation evidence and final release acceptance
remain open. This checkpoint creates no acceptance PR or production promotion.

### Phase 5 resource edges, roster evidence and fixture ownership

After `c7208fc`, open_database_cursor owns a cursor while borrowing its connection.
Its existing complete_cleanup path attempts close once and retains the original
query failure/cause, cancellation or interruption; close-only failure still
propagates. Team-stint planning/applying and cached CapWages summary reads use
this guard. The summary's outer transaction retains commit/rollback/connection
ownership. Native HTTPError response objects raised by roster urlopen are now
explicitly closed, with close failures recorded as secondary to the HTTP error.

Roster fetch_validated moved unchanged from pure util to the HTTP adapter, with
both actual feed callers updated. AST comparison confirms its complete
signature/body, all team-stint SQL assignments and the summary SQL/report strings
are unchanged. Classification now takes one RosterEvidence containing immutable
membership frozensets and completeness facts; the mutable match dictionary does
not cross that boundary. LTIR/active/minors/unknown and incomplete-feed behavior
remain unchanged. Dedicated IntegerValueViolation/TeamAbbreviationViolation
leaves preserve native Pydantic ValueError integration and original safe messages
while exposing typed input context to callers.

Review also found three disposable engine fixtures whose setup could fail before
yield without disposal. Contract, source and API fixtures now put setup/yield
inside the production resource guard with explicit disposable Dev settings. The
source fixture delegates transactions to the production guard instead of copying
weaker Exception-only cleanup. Integration resource probes use the same cursor
and transaction ownership. Fixture pools now use the explicit project resource
settings, and no external database or source ingestion is involved.

Verification under Python 3.12.14:

- Before fixes, 42 cursor and four native HTTPError regressions produced **28
  failures, 18 passes**. Final focused resource/roster/source units passed
  **171**, including native typed-validator context and safe-message cases.
- After the fixture ownership fixes, fresh migrated
  `tradevalue_test_logging05_resource_edges_final2` passed **1,317 tests, zero
  skips**, **91.20%** aggregate coverage in **129.86 seconds**, and the
  **100%** API/calendar gate. Isolated units passed **1,267**, with 50
  integrations deselected, in **111.64 seconds**. The earlier final run is
  superseded by final2 for fixture ownership evidence.
- Locked sync, Ruff lint/format, ty, structural scope, requirements exports,
  OpenAPI parity, migration history/preflight/schema snapshot, API smoke, clean
  API/Vercel/ML artifacts, exclusions and committed-model gates pass.
- Rebuilt `tradevalue-logging05-resource-edges:verified` runs as UID 10001 against
  fresh `tradevalue_test_logging05_resource_edges_probe`. INFO/JSON and DEBUG/text
  each pass six HTTP/streaming flows with **15 / 22** captured events and
  graceful exit **0**; invalid startup produces CRITICAL and exit **3**.
  Probe containers are removed. Later fixture edits are excluded from the API
  artifact; distributed runtime/build inputs match the rebuilt image.
- Diff whitespace and prohibited-form searches pass. No new comments,
  suppressions, dependencies, frontend, public HTTP schema or committed model
  artifacts changed.

Transcripts use `/private/tmp/tradevalue-logging05-resource-edges-` prefixes.
The authoritative full script is `tradevalue-logging05-resource-edges-final2-checks.sh`;
image script/captures use `tradevalue-logging05-resource-edges-image-checks.sh`
and `tradevalue-logging05-resource-edges-capture`. Source comparison is
`tradevalue-logging05-resource-edges-move-check.py`; red evidence is
`tradevalue-logging05-resource-edges-red.txt`.

The source ledger now records 237 files: 18 empty, 20 docstring-only, **161**
other inspected and **38** test files pending. Inspected does not mean every
finding is accepted. Source inspection helper ROOT paths still resolve during
import and should defer filesystem work; the real HTTP/log verifiers should
assert exact ID/error-severity shapes and stronger response-body evidence before
combined acceptance. Legacy role/interface and precise framework/historical
choices remain open, along with hosted NonProd success/mode/correlation evidence
and final release acceptance. No acceptance PR or production promotion is made
by this checkpoint.

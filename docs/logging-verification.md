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
The dedicated checkpoint PostgreSQL container was removed after verification.

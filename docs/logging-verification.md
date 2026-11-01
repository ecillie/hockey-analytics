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

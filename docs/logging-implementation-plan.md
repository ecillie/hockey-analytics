# Repository wide logging implementation plan

Add consistent operational logging across the API, browser frontend, ingestion,
ML, and repository commands as the final feature for this release. Normal mode
uses `INFO`; debug mode uses `DEBUG`. Environment selection and log verbosity
remain independent. This plan defines implementation work; it does not change
runtime configuration or authorize deployment.

## Scope and current behavior

The starting tree is phase 7 checkpoint `355c8f6`. Refresh remote state before
implementation and reconcile the remaining Python remediation work through
`Dev`. Logging does not replace phase 7's outstanding semantic review or exact
framework dispositions.

| Area | Current behavior | Required outcome |
| --- | --- | --- |
| API | `backend/src/app/main.py` logs database and unhandled errors. Docker starts the Uvicorn application factory; `backend/index.py` exports the Vercel app. | Consistent startup configuration, request correlation, request summaries, safe error diagnostics and shutdown events on both hosting paths. |
| Ingestion | Command entrypoints configure `INFO`; `ingestion.py` warns when retaining previous contract data. Run status is stored separately in `ingestion_runs`. | Correlated run and stage events, retry and recovery diagnostics, committed counts, rollback outcomes and incomplete-source failures. |
| ML | Entrypoints configure `INFO`, log failures and print requested reports. | Data loading, feature construction, training, evaluation and artifact lifecycle events without logging datasets or changing calculations. |
| Repository operations | Export, migration, schema, repair, smoke and structural-check commands have individual logging setup. Alembic uses `fileConfig` and `backend/alembic.ini`. | Shared application log policy with preserved command paths, output and exit behavior; explicit handling of Alembic's configuration. |
| Frontend | `ApiClient` translates API failures; `useApiQuery` handles errors and cancellation. There is no shared browser logger or application error boundary. | Controlled browser diagnostics, API request correlation, render-error capture, and global error handling without duplicate reports or cancellation noise. |
| CI and deployment | Hosting captures process output; verification already checks CLI contracts, imports, packages, containers and frontend coverage. | Tests and runbooks prove both modes across supported entrypoints and preserve existing release gates. |

Instrument operational boundaries rather than every function. Generated files,
dependencies, source datasets and archived `.py.txt` loaders do not need logging
code. Bash workflows retain their native output; audit changed commands for safe
diagnostics and avoid shell tracing around credentials.

## Modes and configuration

| Setting | Proposed contract |
| --- | --- |
| `ENV` | Existing `dev`, `nonprod`, or `prod` selection; retain current configuration precedence. |
| `LOG_LEVEL` | `INFO` by default in every environment. Normal mode emits INFO, WARNING, ERROR and CRITICAL. `DEBUG` adds diagnostic events. Accept the five standard level names as explicit thresholds, normalize case and whitespace, and reject unknown or empty values. |
| `LOG_FORMAT` | `json` by default for Python diagnostics; optional `text` for local terminal use. Reject unknown values. Format is independent of environment and level. |
| `VITE_LOG_LEVEL` | Browser threshold, default `INFO`, validated at build time. It follows the same severity ordering without depending on whether the build uses mock data. |

Use these examples in environment templates and runbooks:

```text
ENV=prod       LOG_LEVEL=INFO
ENV=nonprod    LOG_LEVEL=INFO
ENV=nonprod    LOG_LEVEL=DEBUG
ENV=dev        LOG_LEVEL=DEBUG LOG_FORMAT=text
```

Provide one threshold authority per runtime. Initially use environment settings
without adding overlapping `DEBUG`, `LOG_MODE`, or command flags. Preserve
`--help` and argument-validation behavior before resource acquisition. Logging
settings must not require a database URL or make OpenAPI generation load dotenv.
Resolve settings from an explicit values mapping: exported environment values
retain precedence over dotenv for entrypoints that already load it, followed by
defaults. Standalone export and verification tools use their existing environment
contract without adding dotenv loading. Do not mutate `os.environ` to configure
logging or silently change database-setting precedence.

Browser `VITE_*` values are public build configuration. Changing the frontend
threshold requires a new build; changing Python settings requires a process
restart or deployment. A debug threshold must not enable FastAPI debug error
pages, expose tracebacks in HTTP responses, change data access, or select a
different database.

## Startup ownership and Python rules

The current global Python rule says: **"Only `main()` configures logging
(handlers, levels, formatters). Importable modules never call `basicConfig` or
attach handlers."** Application commands can follow this directly, but the
Uvicorn factory and Vercel ASGI export do not invoke an application CLI `main()`.

Proposed owner decision: allow installation of the shared logging configuration
once at the hosted API's explicit startup boundary, while ordinary imports and
`create_app()` remain free of handler installation. Record the exact approved
hook and its import/startup behavior before implementing that exception. If the
rule must remain literal, choose a supported host-owned logging configuration
for both Docker and Vercel and prove it works. Renaming a helper to `main()` is
not a substitute for resolving ownership.

Shared code should construct frozen settings, formatters and configuration
values. CLI `main()` functions install that configuration. Libraries only obtain
their module logger and emit events. Startup must preserve host loggers, avoid
duplicate handlers on repeated initialization, and never use unconditional
`force=True` to replace logging owned by a host or test harness.

Prefer the standard library and existing dependencies. Use a small shared
package such as `backend/src/app/shared/observability/`, with role files for
settings/domain values, boundary validation, record formatting and policy.
Keep it independent of ingestion, ML, tests and database creation so the serving
wheel can include it safely. Locate applicable configuration instructions before
changing tool or deployment configuration.

## Event contract and severity

Python JSON events use one record per line on stderr. Keep the same fields when
the threshold changes. Required fields are UTC timestamp, severity, stable event
name, logger/component, environment when known, and a controlled human-readable
message. Add release identity from existing deployment metadata when available;
do not shell out to Git or require hosting credentials to obtain it.

Optional context includes request ID, command invocation ID, durable ingestion
run ID, stage, source, season, outcome, HTTP method, route template, status,
duration in milliseconds, attempt number and aggregate counts. Use monotonic
time for durations. Keep event names stable; use structured fields for variable
values. A command invocation ID must work even before a durable run exists.

| Level | Meaning and examples |
| --- | --- |
| DEBUG | Safe page/batch progress, retry decisions, worker-stage details, validation counts and timing breakdowns. Avoid one event per row. |
| INFO | Startup readiness, completed requests, command/stage completion, successful writes and artifact creation. Routine validation errors and missing resources belong in request summaries. |
| WARNING | A recoverable degradation such as retrying a transient source failure or deliberately retaining a last-good snapshot. |
| ERROR | A failed request, job, verification or stage requiring an error result. Emit the exception diagnostic once at the boundary that translates it to a response or exit code. |
| CRITICAL | The current service/process cannot function, such as unrecoverable startup failure. An individual request failure is not automatically critical. |

An access summary and an exception diagnostic are distinct events. Do not emit
the same exception traceback from the repository, service, middleware and
command layers. Document failure ownership for each flow and test framework
propagation so Uvicorn or Starlette does not create avoidable duplicate reports.
Do not suppress unrelated host error records to achieve deduplication.

## Sensitive data and output policy

Allowlist structured context fields. Neither mode may emit credentials, tokens,
cookies, authorization headers, database URLs, feed keys, complete query strings,
request/response bodies, SQL parameters, dataframe contents or model payloads.
Use route templates and upstream source names rather than full URLs. Browser
events must also exclude location queries/fragments and user-entered search text.

Exception messages, chained exceptions, cleanup notes and third-party records
can contain sensitive values. Preserve traceback and cause diagnostics through
a safe serializer: include exception type/code and stack frames without locals,
using module names or project-relative paths where possible. Sanitize any
retained messages or notes before output. Do not rely solely on a
password regex or SQLAlchemy parameter hiding. Test hostile nested fields,
connection errors, HTTP exceptions and malicious control characters in both
formats and at both thresholds.

Bound record size and collection/string lengths with documented frozen options.
An initial proposed record ceiling is 8 KiB; verify it against the deployed sink
and mark truncation explicitly. Formatting must handle missing context and
non-serializable values without changing an API response, job result, exception
identity, transaction outcome or command exit status. Do not add unbounded
logging queues or background delivery tasks.
Unknown objects must use a safe type marker rather than unrestricted `str()` or
`repr()`. Test formatter and sink failures, with a bounded safe fallback that
does not recursively log or dump the raw record through logging's own diagnostics.

Existing command JSON and requested reports stay on stdout as specified in
[Python command contracts](python-commands.md). Adding diagnostics must not turn
a single JSON result into mixed log/report output. Logging redaction does not
silently redefine those requested reports or rewrite stored ingestion records.

## API instrumentation

Add a request ID generated by the application, return it as `X-Request-ID`, and
include it in access summaries and error diagnostics. Ignore caller-supplied
request IDs initially, so arbitrary header content cannot enter diagnostics.
Expose the response header through CORS when the configured frontend needs it.
Keep existing response bodies, statuses, CORS origin restrictions and OpenAPI
semantics intact; document the additive header contract.

Use an ASGI implementation that preserves streaming and cancellation without
buffering bodies. Verify its position relative to CORS and framework exception
handling. Capture the final outcome for successful, invalid, missing-route,
database-error and unexpected-error responses, including failures after response
headers begin. Request IDs must be present on error responses too.

Emit ordinary request completion at INFO and safe diagnostic detail at DEBUG.
Suppress successful health probes from normal access summaries, but retain
failed health checks. Configure Uvicorn access logging deliberately to avoid a
second application access stream. Keep SQL/HTTP dependency debug logging from
dumping parameters or upstream secrets when application DEBUG is enabled.

Add startup-ready and shutdown events. Include safe cleanup diagnostics while
preserving existing timeout, cancellation and primary-failure behavior. Request
context must not leak across concurrent requests, lifespan instances or tests.

## Ingestion ML and operational instrumentation

Ingestion events cover command start/end, source stages, bounded page/batch
progress, retries, quality failures, roster completeness and retained snapshots.
Distinguish fetched, validated, attempted, committed and rolled-back counts.
Do not log a successful write before the owning transaction commits. Preserve
independently committed historical batches when reporting a later failure, and
preserve whole-transaction rollback for incomplete roster feeds.

Use existing run IDs after allocation and a command invocation ID beforehand.
Pass immutable context into worker jobs, or use explicitly owned context with
per-job propagation and cleanup. Thread-pool work must retain its own source,
stage and run context without introducing a module-level mutable context store.
Logs supplement `ingestion_runs`; they do not replace its durable status or add
a logging database schema.

ML events cover dataset loading/validation, feature construction, training
splits, evaluation, metadata checks and artifact writes. Log counts and approved
aggregate metrics rather than player rows or predictions. Keep pure calculation
functions silent and instrument orchestration boundaries. Retain existing
stdout diagnostics, model semantics and artifact formats.

Migrate every supported command listed in `docs/python-commands.md`, plus
`backend.database.verify_python_rules`, to the same configuration contract.
Include success, dry-run, verification-failure, incomplete-feed, cancellation
and cleanup-failure paths. Keep frozen migration revisions unchanged; reconcile
Alembic's existing configuration in `backend/migrations/env.py` and
`backend/alembic.ini` without adding duplicate handlers or disabling host loggers.

## Frontend instrumentation

Add a typed logger under a shared frontend logging directory, initialized from
`frontend/src/main.tsx`. Normal mode supports the same five severity names; map
CRITICAL to an appropriate console method while preserving its severity field.
DEBUG adds safe lifecycle and request diagnostics. No secrets belong in Vite
configuration or browser logs.

Validate `VITE_LOG_LEVEL` in the Vite build configuration and reuse the same pure
level parser for browser initialization. Do not infer Prod versus NonProd from
Vite's build mode or mock-data selection; include deployment environment metadata
only when it is explicitly available.

Instrument `frontend/src/api/client.ts` for network, HTTP, decode and unexpected
response failures. Attach the server request ID when present without changing
the existing error body contract. AbortController cancellation is expected
behavior and must not produce warning/error events. Choose one reporting owner
across the client, `useApiQuery`, render boundary and global listeners.

Add an application render-error boundary with an accessible fallback, plus
`error` and `unhandledrejection` listeners for failures outside React rendering.
Keep existing page-level error and retry UI. Register listeners once, provide
cleanup, and verify development StrictMode does not duplicate events. Bound
repeated browser error reports so a failure loop cannot flood diagnostics.

The initial browser sink is the local console. API request IDs link browser API
failures to server diagnostics; browser-only failures will not appear in server
logs. If centralized browser collection is required for this release, decide
that before the frontend phase and include its transport, authentication, rate
limits, retention and delivery-failure tests. Do not imply console events are
centrally retained or add a paid collector implicitly.

## Delivery phases

Each implementation PR targets `Dev`. Start feature branches from freshly
fetched `origin/Dev` and include required preceding work through `Dev` before
starting a dependent phase. Preserve the local historical `plan.md`. Keep tests
with the behavior they verify rather than deferring them to the final phase.

| Phase | Branch | Deliverables and completion gate |
| --- | --- | --- |
| Logging 1 Shared policy and startup | `feature/logging-01-foundation` | Resolve the API startup rule decision; implement frozen settings, safe formats, field policy and host/CLI configuration ownership. Verify default/override/invalid settings, level filtering, exception sanitization, repeated setup, silent imports and no database dependency. No supported host may be left without a viable bootstrap design. |
| Logging 2 API | `feature/logging-02-api` | Request IDs, access/error/lifecycle events, health handling and host access-log coordination. Verify concurrency, all response/error paths, streaming, cancellation, CORS exposure, safe stacks and unchanged HTTP bodies in both modes on Docker and the Vercel entrypoint. |
| Logging 3 Jobs and commands | `feature/logging-03-jobs-commands` | Ingestion, roster, contracts, ML and every operational entrypoint; Alembic configuration reconciliation; command documentation. Verify stdout/exit compatibility, retry/fallback ownership, worker context, commit-aware summaries and cleanup failures using fakes and disposable PostgreSQL. |
| Logging 4 Frontend | `feature/logging-04-frontend` | Browser logger, API correlation, render boundary, global listeners and mode documentation. Verify all severities, safe fields, missing request IDs, malformed responses, expected aborts, listener cleanup, duplicate suppression and existing user flows at unchanged coverage thresholds. |
| Logging 5 Release acceptance | Final combined Dev candidate | Reconcile all phases, finish the event/entrypoint inventory, run the complete gates below and complete the deployment/runbook checks. Open a final Dev-targeting fix/docs PR if needed. Promote only through the normal release workflow and retain manual production approval. |

## Verification and release gates

For every Python implementation change run:

```bash
uv sync --locked --all-groups
uv run ruff check
uv run ruff format --check
uv run ty check
uv run python -m backend.database.verify_python_rules
uv run pytest
```

The full pytest run must use a newly provisioned disposable local PostgreSQL
database named `tradevalue_test...` and finish with zero skips. Preserve the
58.80% aggregate floor and the 100% API/shared-calendar behavior gate. Use
fixture-driven behavior tests and property-based adversarial redaction tests;
place shared support under excluded concept test packages. Test logging
configuration in isolated processes where global handler state would otherwise
make tests order-dependent.

Also run the isolated unit selection with database URLs absent and dotenv
disabled, the committed ML gate, dependency export parity, OpenAPI and generated
TypeScript parity, isolated package installs, and wheel/sdist boundary checks.
The API wheel must retain shared logging support while excluding ingestion,
ML and test support. Prove the installed ML package can use the shared logger
through its declared backend dependency.

Run frontend contract checking, lint, tests and production build. Preserve 100%
statement, branch, function and line coverage for shipped frontend modules;
logging helpers and the error boundary must remain measured even though
`main.tsx` is already excluded as bootstrap code. Apply the React review
checklist after edits to multiple TSX components.

Build and smoke the production container with INFO and DEBUG against the
disposable database. Exercise the Vercel entrypoint in tests without live
upstream ingestion. On an approved NonProd deployment, verify actual captured
stderr, request IDs, severity, formatting, duplicate suppression and safe
diagnostics. Record commit, environment, commands and results for each gate.
Do not mark hosted validation complete based only on a local console capture.

## Deployment runbook and final checklist

Update backend/frontend environment templates, README startup instructions,
`docs/python-commands.md`, `docs/python-verification.md` and
`docs/deployment-vercel-neon.md`. Document where API and job logs are captured,
where browser logs appear, who can access hosted logs, the configured retention,
and how to correlate a request or run. Verify platform-specific retention and
limits during rollout rather than assuming a hosting plan's behavior.

Use INFO for the release baseline in NonProd and Prod. Document how to enable
DEBUG for troubleshooting, restart/redeploy the relevant runtime, and restore
INFO afterward. Keep database/environment selection unchanged. Rollback must
restore the previous configuration or artifact without a schema migration.

Release completion requires evidence that:

- Every supported entrypoint and operational boundary has an event owner and
  is implemented, or has an explicit reason to remain silent.
- Both modes work on every runtime; missing configuration defaults to INFO and
  invalid configuration fails clearly before external resources are acquired.
- Secrets, payloads and SQL parameters remain absent from emitted diagnostics,
  including formatted exception chains and third-party messages.
- Requests and concurrent job stages retain the correct correlation context;
  expected cancellations and handled failures do not produce duplicate errors.
- API responses, CLI stdout, exit codes, transactions, model artifacts and
  coverage thresholds retain their documented contracts.
- Existing phase 7 acceptance and all logging phase gates are complete; the
  combined release candidate passes local and required hosted checks.
- API startup ownership is explicitly resolved, browser collection scope is
  clear, and logging locations, retention, debug activation and rollback are
  documented before production approval.

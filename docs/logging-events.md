# Logging event owners

Python diagnostics use stderr; requested CLI reports and offline migration SQL
retain their stdout contracts. Application log delivery is disabled for
`ENV=nonprod` and `ENV=prod`, including browser builds made with those values.
Dev uses the configured log levels. Native platform telemetry has its own owners.

## Browser

The application bootstrap owns one logger and one pair of global listeners,
outside React effects. Cleanup removes its listeners and deactivates its logger;
hot reload also unmounts its root. Imports do not install listeners or emit logs.
React root callbacks own render-error reporting; the error boundary displays a
generic fallback. Handled API failures retain the existing page retry behavior.

| Events | Owner and severity |
| --- | --- |
| `app.started` | Application bootstrap, INFO |
| `api.request_started`, `api.request_finished` | API client, DEBUG |
| `api.request_cancelled` | API client, DEBUG; original cancellation preserved |
| `api.request_failed` | API client, ERROR; controlled network/HTTP/decode/invalid-response/unexpected category |
| `react.render_failed`, `react.uncaught_error`, `react.recovered_error` | React root callbacks, ERROR / CRITICAL / WARNING |
| `global.error`, `global.unhandled_rejection` | Owned window listeners, ERROR; expected aborts silent |
| `logging.suppressed` | Logger, at the suppressed severity |
| `logging.format_failed` | Independent formatter fallback, at least ERROR; CRITICAL retained |

`VITE_LOG_LEVEL` is validated at build and bootstrap, default INFO, with the same
five severity thresholds and case/whitespace normalization as Python. Browser
output is one JSON string per console call, using debug/info/warn/error methods;
CRITICAL uses console.error with its severity retained in the record. There is
no browser text format or hosted collection. No deployment environment is inferred
from Vite mode or mock selection; optional logger environment metadata accepts
only explicit dev/nonprod/prod values.

The logger permits only stable events, components, categories, route templates,
numeric status/duration and exactly 32 lowercase hexadecimal server request-ID
characters. It never serializes errors, stacks, messages, URLs, query values,
headers, bodies or nested objects. HTTP errors retain their original UI message,
code and details; their new optional `requestId` carries the validated correlation
ID. Decode exceptions and cancellation reasons preserve their identity. Unknown
paths become `unknown`, and malformed correlation IDs are omitted.

Each logger permits 20 records per severity per monotonic 60-second window plus
one suppression notice for that severity. There are five finite counters, no
queue, persistence or retries; DEBUG traffic cannot consume ERROR capacity.
Object errors are deduplicated in a logger-owned WeakSet, including errors that
subsequently reach a root/global handler. Primitive rejections are bounded by the
rate limit. Expected aborts are not error diagnostics. Sink/format/clock faults
do not replace API or render results, and a failed sink does not recursively log.
Global handlers prevent the default raw error console report while allowing
other listeners to run. Browser-native network or extension diagnostics remain
under browser ownership; this policy governs application records.

## Configuration and correlation

`LOG_LEVEL` defaults to INFO; DEBUG adds detail without changing environment,
database, calculation, transaction or artifact selection. `LOG_FORMAT` defaults
to JSON; text uses the same escaped fields with a terminal prefix. Application
commands configure logging only from `main()`. The approved API lifespan hook
configures hosted ASGI entrypoints. Imports and OpenAPI app construction do not
install handlers. The shared handler does not replace root handlers.

| Entrypoint | Owner/source |
| --- | --- |
| Uvicorn factory and `backend/index.py` | API lifespan bootstrap; per-request generated `request_id` |
| `backend/export_openapi.py` | `openapi` |
| Seven operational database commands, including structural verification | Command basename, such as `migration_preflight` or `verify_python_rules` |
| Complete ingestion runner | `ingestion` |
| Roster-status command | `roster_status` |
| Historical contracts command | `historical_contracts` |
| Nine ML commands | `ml.` plus command basename; the committed metric gate uses `ml.metric_gate` |
| Alembic migration environment | `alembic`; native help and operations that never load the environment retain framework output |

Commands generate an `invocation_id` before external resource acquisition.
Ingestion enriches an immutable context with source, stage and durable `run_id`,
then passes it into services, transaction factories and workers. No global mutable
request/job registry is used. Custom injected resource factories retain ownership
of their own observation hooks.

## API

| Events | Owner and severity |
| --- | --- |
| `request.started` | ASGI request middleware, DEBUG |
| `request.finished` | ASGI request middleware, INFO; successful health probes and expected cancellation are DEBUG |
| `request.failed` | Translating API handler, ERROR; propagated host duplicate consumed once. Unhandled streaming failures are diagnosed once by the coordinated host. |
| `request.cancelled` | Coordinated host boundary, DEBUG |
| `service.ready`, `service.stopped` | Lifespan protocol wrapper, INFO |
| `service.startup_failed`, `service.shutdown_failed` | Safe ASGI failure transport to host; CRITICAL / ERROR |
| `service.startup_cancelled`, `service.shutdown_cancelled` | Safe ASGI failure transport to host, DEBUG for pure cancellation |

IDs replace caller-supplied IDs and are exposed through configured CORS. Request
summaries retain final status/outcome and monotonic duration, including failure
after streaming headers. Matched route templates replace raw paths and queries.
Access summaries and exception diagnostics are separate records. Uvicorn's extra
access stream is disabled; unrelated host errors remain visible.

## Commands, ingestion and transactions

| Events | Owner and severity |
| --- | --- |
| `command.started`, `command.finished` | Shared command boundary, INFO; cancelled completion is DEBUG |
| `command.failed` | Exception-to-exit translation or process-owned unhandled hook, ERROR, once |
| `command.cancelled` | Process-owned unhandled hook, DEBUG; cancellation still propagates |
| `command.verification_failed` | Verification boundary, ERROR, with controlled stage/module/line fields where applicable |
| `ingestion.started`, `ingestion.finished` | Durable run tracker, INFO; pure cancellation finish is DEBUG |
| `ingestion.validated`, `ingestion.roster_completed` | Source/command orchestration, INFO; classification precedes transaction completion |
| `ingestion.rows_read`, `ingestion.page_read`, `ingestion.profiles_fetched`, `ingestion.feed_received` | Aggregate source progress, DEBUG |
| `ingestion.worker_started`, `ingestion.worker_finished` | NHL worker boundary, DEBUG; season, kind and game type only |
| `ingestion.request_started`, `ingestion.retry_scheduled` | HTTP boundary, DEBUG; no URL, parameters or payload |
| `ingestion.request_recovered` | Native adapter retry history, WARNING; attempt count only |
| `ingestion.fallback_started`, `ingestion.fallback_finished` | Profile fallback boundary, DEBUG |
| `ingestion.fallback_summary`, `ingestion.snapshot_retained` | Batch/pipeline recovery boundary, WARNING |
| `ingestion.batch_started` | Historical batch boundary, DEBUG |
| `ingestion.batch_committed`, `ingestion.batch_previewed` | Historical service after repository scope exits, INFO; preview committed count is zero |
| `transaction.started` | DB-API transaction owner, DEBUG |
| `transaction.committed`, `transaction.rolled_back` | DB-API owner after successful commit/rollback, INFO; pure cancellation rollback is DEBUG |
| `transaction.rollback_failed` | DB-API owner, WARNING; the exception diagnostic stays with the command boundary |

Counts use existing durable data-record counters; they do not include every
internal SQL statement or infer totals from player/team dimensions. Earlier
committed batches remain reported if later work fails. A failed status update
retains known completed-work counts. A transaction commit can be read-only, and
unknown rollback row counts are omitted rather than guessed from input size.

## ML and migrations

| Events | Owner and severity |
| --- | --- |
| `ml.dataset_ready`, `ml.dataset_validated` | CLI/training/evaluation orchestration, INFO, aggregate rows |
| `ml.split_ready` | Training orchestration, DEBUG |
| `ml.training_started`, `ml.training_finished`, `ml.split_evaluated` | Training orchestration, INFO; aggregate rows and validated MAE/RMSE/R2 |
| `ml.evaluation_finished`, `ml.metadata_validated`, `ml.metric_gate_passed` | Evaluation/gate orchestration, INFO |
| `ml.artifact_loaded`, `ml.artifact_written` | Artifact adapter after successful operation, INFO; stage identifies model/metadata/predictions without paths or payloads |
| `migration.mode_selected` | Alembic orchestration, DEBUG |
| `migration.step_rendered`, `migration.step_pending` | Native Alembic callback, DEBUG; pending means the step has run before final commit, not that it committed |

Pure ML transformations and ML library calls without explicitly injected context
remain silent. Alembic commands preserve SQL stdout and exit behavior, including
255 for framework command errors and 1 with `--raiseerr`. Programmatic callers
retain their original exceptions and exception hook. The environment callback
returns control on success; it cannot unconditionally exit the framework process.

## Bounds and failure delivery

Only allowlisted identifiers, aggregate numbers and safe exception types/frames
are serialized. Messages, arguments, exception values, notes, absolute paths,
locals, SQL parameters and payloads are omitted. Records default to 8 KiB with
bounded strings, frames and exception chains, including explicit truncation.
Secondary cleanup diagnostics retain the primary exception. Formatting/delivery
failures use a safe fallback without raw logging error dumps. Hosted sink limits
and retention are controlled by the hosting platform.

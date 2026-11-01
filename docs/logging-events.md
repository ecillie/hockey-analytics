# Logging event owners

Implemented Python behavior through logging phase 3. Browser instrumentation and
hosted retention/access/limit acceptance are later phases. Diagnostics use stderr;
requested CLI reports and offline migration SQL retain their stdout contracts.

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
and retention still require phase-5 acceptance.

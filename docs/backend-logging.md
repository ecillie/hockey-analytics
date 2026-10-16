# Backend logging

The API, replacement setup/backfill entrypoints, jobs, and database helpers share
`app.observability`. Logs are newline-delimited JSON on **stderr**. CLI result
reports remain JSON on **stdout**, with the existing exit behavior: `0` for a
completed run, `1` for incomplete/deferred/failed work, and `2` for invalid
arguments or runtime initialization. No AWS service is needed to use logging.
Frontend logging is outside this release.

## Configuration

Set `LOG_LEVEL` in the process environment or `backend/.env`:

```dotenv
LOG_LEVEL=INFO
```

To also save development logs to a text file, add this to `backend/.env`:

```dotenv
ENV=dev
LOG_LEVEL=DEBUG
LOG_FILE=logs/backend.txt
```

Relative `LOG_FILE` paths are resolved from `backend/`, independent of the working
directory; this example writes to `backend/logs/backend.txt`. Absolute paths also
work, and missing parent directories are created. Leave `LOG_FILE` empty/unset to
disable file output. The standard `backend/logs/` directory is Git-ignored.

The file contains the same sanitized JSON lines as stderr, with UTF-8 encoding.
It rotates at 5 MiB, retaining three backups (`.1`, `.2`, `.3`). Reconfiguration
closes old file handlers and does not duplicate output within either destination.
Use one process per log file; rotating files are intended for local development,
not multiple Uvicorn workers sharing a file. File logging is ignored outside
`dev`. Job/setup CLIs use their explicit `--environment`, so an ambient `ENV=dev`
cannot enable a file for a production job. Argument parsing uses stderr only.
An unusable configured dev file stops startup with a sanitized error rather than
silently dropping file output.

Allowed levels are `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`.
Invalid configuration fails before execution with a message that does not echo
the supplied value. `INFO` is the default. Use `DEBUG` for batch validation,
accepted counts, committed checkpoints, successful source requests, and database
connection/commit events. Failures and retries remain visible at warning/error
levels. Raising the threshold can intentionally suppress lower-severity events.

The API application factory and replacement job/setup/backfill CLIs configure
logging. Imports of job/support modules do not configure logging, run work, or
connect to a database. A program that embeds these libraries should call
`configure_logging()` once at its process entrypoint and supply explicit job
configuration as usual. Logging configuration loads no database credentials;
the CLI loads the existing backend environment configuration before configuring
its logger.

Configuration replaces existing process/root and named-logger handlers with a
shared stderr handler and the optional dev file handler. It closes its own old
handlers while preserving externally owned streams. Reconfiguration does not
accumulate handlers. Uvicorn access logging is disabled because the request
middleware emits the request record. Configure logging before concurrent work;
avoid adding a separate formatter/handler afterward that prints raw dependency
messages. Cloud log collector configuration and retention are later launch work.

## Log fields

Every record includes UTC `timestamp`, `severity`, `component`, `environment`, and
`event`. Missing/invalid ambient `ENV` is labeled `unknown`; explicit job
environments override the ambient value in job diagnostics.

| Context | Fields and events |
| --- | --- |
| API request | Internal UUID `request_id`, HTTP method, matched route template, status, and `duration_ms`; `api.request_completed` or `api.request_cancelled` |
| API errors | `api.validation_failed`, `api.problem`, or `api.database_error`, linked by request ID; unhandled exceptions are summarized on the request completion record |
| Job | `job_run_id` matching the persisted run, job, mode, environment, seasons, game types, correction lookback, resume flag, counts, elapsed time, and terminal status |
| Setup/backfill | `setup_run_id` shared by all child-job logs; requested/completed partition counts, completion flag, and elapsed time |
| Source requests | Source name, attempt, HTTP status when available, bounded retry delay, and failure type; no URL or response body |
| Persistence | Batch ID, job run ID, upload retries/failures, checkpoint completion/count, and transaction outcome; no SQL or checkpoint cursor contents |
| GitHub Actions | Validated numeric `github_run_id`/`github_run_attempt` and hexadecimal `github_sha` when present on setup/job runs |
| Exception | Exception-chain types and bounded stack locations: filename, line, function; no exception text, source lines, locals, SQL, or parameters |

Request IDs are generated internally, isolated across concurrent requests, and
reset at completion/cancellation. Incoming headers are not trusted as IDs. No
request/response headers, routes, response bodies, or public API schemas are
changed. Unknown request paths are recorded as `unmatched`; dynamic identifiers
are represented by their declared route template.

A request record looks like this:

```json
{"timestamp":"2026-10-14T20:15:00Z","severity":"INFO","component":"api","environment":"dev","event":"api.request_completed","request_id":"57ec92ca-3c0d-40c2-8c39-26b442bd2342","method":"GET","route":"/api/players/{player_id}","status_code":200,"duration_ms":8.4}
```

Job terminal states distinguish `succeeded`, `no_change`, `partial`, `failed`,
`cancelled`, `deferred`, and `disabled`. Logs describe execution and committed
progress; they do not establish complete upstream coverage or durable database
behavior beyond the configured adapter's guarantees. A hard process kill can
prevent final logs; persisted checkpoints remain the recovery authority.

## Sensitive-data handling

Logging uses registered event names and an allowlist of typed metadata fields.
It does not emit arbitrary message interpolation, raw record extras, exception
messages, stack source text, request bodies, headers, query strings, database
URLs, SQL parameters, source payloads, or checkpoint cursors. Raising `LOG_LEVEL`
to `DEBUG` does not enable those values. SQLAlchemy also hides statement
parameters in its exception formatting.

Other libraries' messages are represented as `library_log`, with component,
severity, correlation context, and sanitized exception locations if available.
Their free text and arguments are intentionally omitted because they can contain
credentials, complete SQL statements, URLs, or source records. This includes
Uvicorn error output, HTTP client diagnostics, and captured Python warnings.
New application diagnostics should use a registered `log_event()` and explicitly
allowed metadata fields rather than adding free-form payload logging.

Public CLI summaries retain run IDs, status, counters, known validation issue
codes/IDs, and source coverage counts. Free-text errors/issue messages and
coverage limitations point to stored records. Raw committed cursors are replaced
by an empty `committed_cursors` list plus `checkpoint_count`. Detailed in-process
`RunReport`/`report_payload()` contracts and persisted review records remain
available to trusted consumers; do not print or upload them as public workflow
artifacts. Those records may contain source observations and invalid input.

## Local use and failure diagnosis

From the repository root, run the offline fixture job without database writes to
an external service:

```bash
PYTHONPATH=backend LOG_LEVEL=DEBUG python3 -m app.jobs.teams_seasons \
  --environment dev --current-season 2026 --validation-only \
  --runtime tests.execution_fixtures:create_runtime \
  > /tmp/tradevalue-job-report.json 2> /tmp/tradevalue-job-logs.jsonl
```

Run the offline setup through the same logging path:

```bash
PYTHONPATH=backend LOG_LEVEL=DEBUG python3 -m app.database_setup.run_setup \
  --environment dev --current-season 2026 --first-season 2026 \
  --jobs teams_seasons player_profiles team_rosters --validation-only \
  --runtime tests.execution_fixtures:create_runtime \
  > /tmp/tradevalue-setup-report.json 2> /tmp/tradevalue-setup-logs.jsonl
```

For an API failure, locate the request completion record by status/time, then
follow its `request_id` to any validation/database event. Use the exception type
and stack location to identify the failing code without exposing input values.
For a job, start with `job.finished`, its counts/status, and `job_run_id`. Follow
that ID through validation, retry, persistence, and resume events. A setup ID
links the child runs; GitHub run/attempt/commit fields link them to workflow output.
For a held record or unavailable coverage, use the issue/run ID to inspect the
access-controlled stored evidence. Investigate a `deferred` job's registered
operation, prerequisites, or writer reservation before retrying.

A retry preserves the existing bounded retry behavior; logging does not change
accepted data, advance checkpoints, acquire extra database connections, or
activate schedules. Review successful committed checkpoints before resuming an
interrupted initial load/backfill. Actual recovery, AWS log routing, retention,
and alerts must also pass the later live-integration gates.

## Verification

```bash
PYTHONPATH=backend python3 -m pytest --no-cov -q \
  backend/tests/test_observability.py backend/tests/test_api.py \
  backend/tests/test_execution_foundation.py backend/tests/test_source_requests.py
python3 backend/export_openapi.py --check
```

Tests use fixtures, mocked database calls, and ASGI/CLI execution. They cover
concurrent contexts, cancellation, retries, committed/resumed progress, malformed
input/JSON, dependency/SQL exception redaction, CLI stream separation, and
idempotent logging configuration, dev file contents/rotation/retention, closed
file handlers, invalid file paths, and enforcement of dev-only file output.
No AWS connection is made.

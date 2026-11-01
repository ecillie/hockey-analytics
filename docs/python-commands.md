# Python command contracts

Run commands from the repository root after `uv sync --locked --all-groups`.
Every command below supports `--help`, rejects unknown arguments, and validates
arguments before opening database or HTTP resources. Importable entrypoints
expose `build_parser()` and `main(argv=None)`; callers should invoke the underlying
use case rather than another command's `main()`.

All 20 application commands, including the ingestion and ML entrypoints and
`backend.database.verify_python_rules`, now use the shared Python logging policy.
They default to `LOG_LEVEL=INFO` and `LOG_FORMAT=json`; DEBUG adds diagnostics,
and text format is available for terminals. Invalid logging settings exit 2
before resource acquisition. Help and argument errors retain their existing
behavior before logging setup. Each invocation generates an `invocation_id`;
`command.started`, `command.finished` and translated failures share it. Output
and exit contracts below remain unchanged. Alembic framework logging and final
phase-3 acceptance are still in progress.

OpenAPI, container readiness, migration history, migration preflight, schema
snapshot and structural verification read logging settings directly from the
process environment without loading dotenv. API migration smoke and team-stint
repair follow the application dotenv/exported-value precedence. Environment and
verbosity remain independent. Python configuration changes require a new process.
ML commands also follow application dotenv/exported-value precedence, except the
standalone metric gate, which reads explicit process values without dotenv.
Ingestion commands also retain application dotenv/exported-value precedence.
The structural checker reports bounded `source_module`, `line` and `stage` fields
instead of serializing arbitrary source diagnostics. Preflight verification
failures use `stage=unversioned_schema` or `stage=multiple_revisions`: review the
schema and follow the documented baseline-stamping procedure before migrating
an unversioned database; resolve conflicting revision records before continuing.

ML commands report aggregate dataset row counts. Training reports temporal split
counts at DEBUG, fit boundaries and validated split metrics at INFO. Evaluation
reports aggregate rows and metrics; artifact events identify model, metadata or
predictions by stage without logging their paths or contents. Each artifact-written
event follows its completed write, so a later metadata failure can leave an earlier
model write recorded without claiming the whole bundle succeeded. Library callers
may inject an immutable invocation context explicitly; existing calls without one
remain silent and retain their existing results. Metadata formats, model options,
predictions and requested stdout reports are unchanged.

Ingestion passes immutable invocation/source/stage context to services and
workers, adding the durable `run_id` after allocation. `ingestion.started` and
`ingestion.finished` describe each tracked source job. Failed job summaries do
not emit another exception diagnostic. Cancellation summaries are DEBUG-only.
Successful summaries report counts from the existing durable `records_read`,
`records_created` and `records_updated` fields when available, rather than
guessing write counts from dimensions such as player or team totals.

Historical batches emit `ingestion.batch_committed` after their repository
transaction exits successfully; `ingestion.batch_previewed` reports zero
committed writes. A later failed batch preserves and reports earlier committed
progress. Profile retry decisions and fallback details are DEBUG events; batch
fallback summaries and deliberately retained last-good snapshots are WARNINGs.
NHL workers include bounded season, player kind and game type fields without
player rows or upstream URLs. Roster feed progress and classification remain
distinct from successful transaction completion. Session cleanup preserves the
original failure/cancellation and retains secondary failure notes.

Commands install a process-owned unhandled-exception hook from `main()` after
logging configuration. Ordinary imports and the API lifespan hook do not replace
`sys.excepthook`. An uncaught cancellation still propagates through resource cleanup
and retains its interpreter exit behavior; only its diagnostic/finished events
are DEBUG. Keyboard interrupts retain SIGINT status (130 in a shell). A genuine
secondary cleanup or status-reporting failure remains visible at ERROR even when
the primary exception is cancellation. Handled execution failures retain their
existing single diagnostic and exit code. Existing cleanup notes stay attached;
safe diagnostics include the first retained cleanup type/frames and explicitly
mark further cleanup detail as truncated, without serializing note text.

`transaction.committed` follows a successful database commit;
`transaction.rolled_back` follows a successful rollback. `transaction.rollback_failed`
reports that rollback itself failed, while the original exception still propagates.
These are transaction outcomes, including read-only transactions, rather than row
write counts. They never infer a rollback row count from attempted input rows.
Default source and contract repository factories carry invocation/run context into
these boundaries; an explicitly injected repository/transaction factory retains
ownership of its own resource instrumentation. If durable run-status persistence
fails after work returned successfully, the failed job summary retains that work's
known completed counters.

| Command after `uv run python` | Options |
| --- | --- |
| `backend/export_openapi.py` | `--check`, `--output PATH` |
| `backend/database/verify_migrations.py` | `--config PATH` |
| `backend/database/migration_preflight.py` | No options |
| `backend/database/schema_snapshot.py` | `--expected PATH`, `--actual PATH`, `--update` |
| `backend/database/migration_smoke.py` | No options |
| `backend/database/container_smoke.py` | `--base-url URL`, `--attempts N`, `--delay SECONDS`, `--timeout SECONDS` |
| `backend/database/backfill_team_stints.py` | `--apply`, `--first-season YEAR`, `--last-season YEAR` |
| `-m app.ScriptingFiles.FullDataScript.run_all` | No options |
| `-m app.ScriptingFiles.FullDataScript.populate_roster_status` | No options |
| `-m app.ScriptingFiles.FullDataScript.capspace` | `--dry-run`, `--apply`, `--coverage`, `--nhl-id ID`, `--player-id ID`, `--first-season YEAR`, `--last-season YEAR`, `--limit N`, `--workers N`, `--batch-size N`, `--force` |
| `-m ml.pipelines.run_pipeline` | `--min-games N` |
| `-m ml.pipelines.load_player_stats` | No options |
| `-m ml.pipelines.load_salary_cap` | No options |
| `-m ml.pipelines.build_model_dataset` | No options |
| `-m ml.features.build_features` | No options |
| `-m ml.features.replacement_level` | No options |
| `-m ml.training.train_skater_value` | No options |
| `-m ml.evaluation.evaluate_skater_model` | No options |
| `-m ml.evaluation.gate` | No options |

Exit status `0` means success; `1` means an execution or verification failure.
Argument errors exit `2`. Roster refresh and the complete ingestion runner also
exit `2` for an incomplete roster feed, preserving rollback and failed-run
tracking. Earlier committed ingestion stages remain committed if a later stage
fails. The runner now reports incomplete roster feeds with the same status as
the standalone roster command.

Successful contract ingestion, roster refresh, complete ingestion, and team-stint
repair write one JSON document to stdout. Other commands write their requested
reports to stdout. Diagnostics and tracebacks use logging on stderr. Verification
failures such as schema drift, missing snapshots, and unsafe unversioned schemas
also use stderr; automation should use exit status to determine success.

Historical contracts and team-stint repair retain their dry-run defaults. The
three historical modes are mutually exclusive. Reversed season bounds and invalid
worker, batch, player, limit, and game-count arguments fail before resource
initialization. Container readiness requires at least one attempt, a finite
nonnegative delay, a finite positive timeout, and an HTTP(S) URL. Readiness polling
remains bounded and reports the last readiness failure.

ML training and evaluation retain their existing artifact defaults and honor
`TRADEVALUE_MODEL_DIR` and `TRADEVALUE_EVALUATION_DIR` at invocation. Importing or
requesting help does not train a model, load a database, or create artifacts.

Application commands use the environment configuration documented in the backend
README. Migration preflight and schema snapshots retain the explicit
`DATABASE_URL`, then `TEST_DATABASE_URL`, precedence. Alembic remains a separate
framework command, invoked with `uv run python -m alembic -c backend/alembic.ini`;
its revision metadata, frozen SQL, and framework logging configuration are
unchanged. Operational scripts remain repository tools; ingestion modules remain
excluded from the serving wheel. CI and database workflows keep their existing
supported paths and flags.

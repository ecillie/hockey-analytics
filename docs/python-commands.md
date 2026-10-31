# Python command contracts

Run commands from the repository root after `uv sync --locked --all-groups`.
Every command below supports `--help`, rejects unknown arguments, and validates
arguments before opening database or HTTP resources. Importable entrypoints
expose `build_parser()` and `main(argv=None)`; callers should invoke the underlying
use case rather than another command's `main()`.

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

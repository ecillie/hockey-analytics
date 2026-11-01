# Python commands

Run from the repository root after `uv sync --locked --all-groups`. Each command
supports `--help` and validates arguments before opening database or HTTP resources.

## Command reference

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

The structural checker is also available as
`uv run python -m backend.database.verify_python_rules`.

## Results and exit codes

| Exit | Meaning |
| --- | --- |
| `0` | Success |
| `1` | Execution or verification failure |
| `2` | Invalid arguments/configuration; roster commands also use it for an incomplete feed |

Contract ingestion, roster refresh, full ingestion, and team-stint repair return
one JSON document on stdout. Other commands print their requested reports.
Diagnostics use stderr; automation should rely on the exit status.

Historical contracts and team-stint repair default to dry-run. Historical
`--dry-run`, `--apply`, and `--coverage` modes are mutually exclusive. Invalid
season ranges, counts, or worker/batch limits fail before resource acquisition.
Container readiness polling is bounded; it requires an HTTP(S) URL, at least one
attempt, a finite nonnegative delay, and a finite positive timeout.

Earlier committed ingestion stages/batches remain committed if later work fails.
An incomplete roster feed rolls back the roster update and records a failed run.
Transaction events describe commit/rollback outcomes, not inferred row counts.

## Configuration and logging

Application commands use the [backend environment rules](../backend/README.md#configuration).
OpenAPI, container readiness, migration history/preflight, schema snapshots,
structural verification, and the standalone ML metric gate read process settings
without dotenv. Other commands use application dotenv/exported-value precedence.
Migration preflight and schema snapshots prefer `DATABASE_URL`, then
`TEST_DATABASE_URL`. Restart the process after changing Python configuration.

Application logging is disabled for `ENV=nonprod` and `ENV=prod`. Otherwise,
`LOG_LEVEL=INFO` and `LOG_FORMAT=json` are the defaults. Invalid logging settings
exit `2` before resource acquisition; help and argument errors run first.

Commands configure logging in `main()` and generate an `invocation_id`. Ingestion
adds source, stage, and durable `run_id` context. Error translation emits one
diagnostic; cancellation still propagates. Keyboard interrupts retain shell
status `130`. Cleanup preserves the original failure and attaches secondary
failures. See [event ownership and safe output limits](logging-events.md).

## ML artifacts

Training/evaluation resolve output paths when invoked, honoring
`TRADEVALUE_MODEL_DIR` and `TRADEVALUE_EVALUATION_DIR`. Imports and `--help` do not
train, open databases, or write artifacts. Library calls remain silent unless
explicitly given an observation context. See the [ML guide](../ml/README.md).

## Alembic

Run framework commands with:

```bash
uv run python -m alembic -c backend/alembic.ini upgrade head
```

Alembic configures logging when its environment callback runs. SQL stays on
stdout and diagnostics on stderr. Native help and early errors keep framework
output. Command errors exit `255` (`1` with `--raiseerr`); other execution failures
exit `1`. Programmatic calls preserve the original exceptions and exception hook.
The callback returns to Alembic on success. Pending step events precede final
commit and do not prove durable success.

Follow the [migration guide](../backend/database/README.md) for preflight checks,
existing database adoption, and revision rules. Operational scripts remain
repository tools; ingestion stays outside the serving wheel.

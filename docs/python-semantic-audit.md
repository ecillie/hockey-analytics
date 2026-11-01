# Python semantic audit checkpoint

This is an incomplete file-by-file review, not phase-7 acceptance. Scope is all
227 Git-tracked Python files at acceptance checkpoint `80bde1a`. Source
digests identify exactly what was inspected; changed files require re-review.
Generated artifacts, environments and retired `.py.txt` loaders are not source
entries. The structural gate separately checks all supported executable roots.

Read `~/.codex/python-guidelines.md` before this review. Mechanical lint, format,
type, structural, test and package results do not waive semantic decisions.
18 empty files and 20 module-docstring-only package files have no executable
behavior to assess. Twenty-nine other files have received the content review
recorded below; unresolved layout/boundary decisions are explicit. Every other
nonempty file remains pending.

Open release decisions include Vercel's exported ASGI application, Alembic's
framework-executed bootstrap, intentional source-only failing test doubles,
ML role layout, and frozen historical migration compatibility. The previously
approved API lifespan logging hook is the only recorded owner approval; this
ledger creates no additional blanket exception.

Review each nonempty file for state ownership and immutability, class/method
placement, Protocol/framework inheritance, narrow types, guards/loop exits, typed
errors and cleanup, await/task/I/O lifetime, main-owned lazy diagnostics and CLI
options, role layout, fixture-driven tests, metadata-only prose and compatibility.
Record findings and fixes before assigning final acceptance.

## Findings requiring resolution

- ML command modules still combine CLI, data access, transformations and reports.
  Complete the role-layout disposition while preserving published module paths,
  stdout, fixed feature order and model artifacts. The content review does not
  declare that layout compliant.
- Metric maps repeat the same raw type across configuration, evaluation and the
  gate. Assess a shared semantic alias and typed key boundary; the type checker
  passing does not resolve the repeated-type guideline by itself.
- The position-to-group mapping is duplicated in model-dataset and feature
  construction. Establish one shared owner or explain the separate information
  boundaries before accepting that duplication.
- Required framework and historical-migration dispositions above remain open;
  do not rewrite frozen history or introduce a global-state approximation.

## File ledger

| Source | SHA-256 prefix | Review disposition |
| --- | --- | --- |
| `backend/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `backend/database/backfill_team_stints.py` | `8cd7c439de15` | Pending semantic review. |
| `backend/database/container_smoke.py` | `fd9ce96e5e2a` | Pending semantic review. |
| `backend/database/migration_preflight.py` | `4307aec8a137` | Pending semantic review. |
| `backend/database/migration_smoke.py` | `64354d6e86c8` | Pending semantic review. |
| `backend/database/migrations/__init__.py` | `efbca4488e57` | Reviewed: module docstring only; no executable behavior. |
| `backend/database/migrations/domain.py` | `2b175b1007fe` | Reviewed: frozen invocation options separate CLI/programmatic and offline/online ownership. |
| `backend/database/migrations/services.py` | `8c2d8f85c21a` | Reviewed: immutable progress callback, NullPool and bounded SQL options, connection/transaction contexts and cleanup preserving original failure; main owns logging, programmatic branch raises without error report. Alembic load boundary remains open. |
| `backend/database/migrations/util.py` | `fdd2ee713f6f` | Reviewed: locally owned controlled dispatch table, typed configuration fields, no exception text copying or import I/O. |
| `backend/database/schema_snapshot.py` | `614a2d92fa7a` | Pending semantic review. |
| `backend/database/verify_migrations.py` | `e2c57a5e94bd` | Pending semantic review. |
| `backend/database/verify_python_rules.py` | `dac613daa2be` | Pending semantic review. |
| `backend/export_openapi.py` | `ea0f876c2f0c` | Pending semantic review. |
| `backend/index.py` | `6a1e64c5ed23` | Reviewed content: required ASGI export calls runtime factory at module load; mutable application and dotenv/factory import work need exact owner disposition. |
| `backend/migrations/env.py` | `68e8ae9c844a` | Reviewed content: thin Alembic-executed main adapter; success returns to framework, failures exit. Load-time bootstrap disposition remains open. |
| `backend/migrations/versions/20260910_0001_initial_schema.py` | `7e09b5e51a37` | Reviewed content: frozen checksum/schema and revision metadata; external reads/SQL only during revision execution. Historical generic guard error, else branch and cleanup contract require frozen-migration disposition; do not rewrite history silently. |
| `backend/migrations/versions/20260920_0002_capspace_source.py` | `935a3ecabd9c` | Reviewed: immutable revision metadata and fixed SQL only in upgrade/downgrade; history preservation included in frozen-migration disposition. |
| `backend/src/app/ScriptingFiles/FullDataScript/capspace.py` | `c71c23f20821` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/__init__.py` | `78dc82a8112a` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/active_repository.py` | `d34803063d7f` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/active_services.py` | `9a5c6bc667fd` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/domain.py` | `29a4813a9d8f` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/errors.py` | `f1256c2dcc7c` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/http.py` | `13604ee9a789` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/options.py` | `1a0520f94707` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/policy.py` | `27bbf289b080` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/reporting.py` | `776416f2c542` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/repository.py` | `956ccc559bd9` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/schemas/__init__.py` | `8c25f29beb35` | Reviewed content: public schema imports and compatibility function aliases only; source-document dependency is separately pending review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/schemas/active.py` | `da783f50d133` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/schemas/contracts.py` | `9c133d82d1a6` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/schemas/documents.py` | `b8e438d701ac` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/schemas/serialization.py` | `d48fc2cec40c` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/services.py` | `43e196d6d0f5` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/__init__.py` | `0e8f75076203` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/fakes.py` | `62e5ed9001dc` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/fixtures.py` | `652dc45a4982` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/postgres.py` | `bc3b22c935c8` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/strategies.py` | `a569707f457d` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/transport.py` | `3d51b48414a0` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/util.py` | `ad4626e15580` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/ingestion.py` | `d7c587a7fa2b` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/ingestion_tracking.py` | `17f8a92976a5` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/populate_roster_status.py` | `5c7d1f03acbf` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/__init__.py` | `e0395eee5ae5` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/ahl_roster_service.py` | `135c28d3585f` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/domain.py` | `0e829827ae62` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/errors.py` | `fcad4786f075` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/http_json_client.py` | `f8d5cfef77c5` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/nhl_roster_service.py` | `373a402fe733` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/policy.py` | `df96de96ad2c` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/repository.py` | `efa87742796e` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/schemas.py` | `3e4461105b5f` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/services.py` | `cf332c14f50c` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/tests/__init__.py` | `ec5000bdb273` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/tests/fakes.py` | `7b5dea773a5e` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/tests/fixtures.py` | `b9523d20a965` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/util.py` | `335e1bc4e70f` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/run_all.py` | `31f350e3526a` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/__init__.py` | `1f506475c98d` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/domain.py` | `d031d85bb39b` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/errors.py` | `58329739d390` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/http.py` | `792b4eee84ae` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/moneypuck/__init__.py` | `92d48982cb80` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/moneypuck/domain.py` | `5cae66cc4ccf` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/moneypuck/repository.py` | `eefdd1931c74` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/moneypuck/services.py` | `5993a60acb67` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/nhl/__init__.py` | `817f46504c4b` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/nhl/domain.py` | `119e2b09304c` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/nhl/repository.py` | `dd3aa97acef7` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/nhl/services.py` | `197f95d02620` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/policy.py` | `3b201cbe5efe` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/repository.py` | `0f8974afd94a` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/schedule/__init__.py` | `a935cb36a63d` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/schedule/domain.py` | `b2439324edef` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/schedule/repository.py` | `2ab1ac0c664a` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/schedule/services.py` | `127956ea8b9a` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/schemas.py` | `951eac4aa966` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/__init__.py` | `2e3fb5387200` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/fakes.py` | `75965991228f` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/fixtures.py` | `ece7fceed4ac` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/identities.py` | `8aed5600a218` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/responses.py` | `015d5898a453` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/scenarios.py` | `142c5682179b` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/strategies.py` | `b39f66564425` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/util.py` | `27e5a7886f23` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/team_stints.py` | `a39bf2c13fcd` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/__init__.py` | `9f4c5a1e1829` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/domain.py` | `f5573df5f967` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/errors.py` | `dffabfa0c590` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/repository.py` | `5286c263386e` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/services.py` | `8bd918e13f25` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/tests/__init__.py` | `512cd1b444a4` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/tests/fakes.py` | `7610a1574dfb` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/util.py` | `51453fb01dc8` | Pending semantic review. |
| `backend/src/app/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `backend/src/app/api/__init__.py` | `ac8dadf50d98` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/api/domain.py` | `207f93061887` | Pending semantic review. |
| `backend/src/app/api/errors.py` | `bd34cb531625` | Pending semantic review. |
| `backend/src/app/api/policy.py` | `8f799d93d8d1` | Pending semantic review. |
| `backend/src/app/api/queries.py` | `eb3a586b0e03` | Pending semantic review. |
| `backend/src/app/api/repository.py` | `4da8ed6f725d` | Pending semantic review. |
| `backend/src/app/api/routes.py` | `26d73f2e592a` | Pending semantic review. |
| `backend/src/app/api/schemas.py` | `d7fbc367ffcc` | Pending semantic review. |
| `backend/src/app/api/service.py` | `b510a125fdce` | Pending semantic review. |
| `backend/src/app/api/tests/__init__.py` | `89699d68cd40` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/api/tests/fakes.py` | `465becfe754e` | Pending semantic review. |
| `backend/src/app/api/tests/fixtures.py` | `8bbfa684ad4a` | Pending semantic review. |
| `backend/src/app/api/util.py` | `f9144c0881f3` | Pending semantic review. |
| `backend/src/app/config.py` | `2e25f8385208` | Reviewed: frozen settings/snapshot, explicit call-time dotenv merge with exports winning, narrow environment selection, typed validation, no import-time external resources. |
| `backend/src/app/database.py` | `bf1fa2396edb` | Pending semantic review. |
| `backend/src/app/main.py` | `5aa95f0094bf` | Reviewed content: native FastAPI extension owns middleware/schema, settings captured at factory, resources owned by lifespan, bounded threaded disposal preserves primary failure. Framework inheritance and approved logging hook are explicit; export/import boundary remains open. |
| `backend/src/app/shared/__init__.py` | `e27164e808fc` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/shared/calendar.py` | `91d7d52a9526` | Pending semantic review. |
| `backend/src/app/shared/cleanup.py` | `45b3252d6b24` | Pending semantic review. |
| `backend/src/app/shared/cli.py` | `321790265705` | Pending semantic review. |
| `backend/src/app/shared/environment.py` | `46b0dac87bab` | Reviewed: explicit operational URL resolver, no dotenv or import I/O, deliberate missing/empty distinction, controlled configuration failures and compatibility function aliases. |
| `backend/src/app/shared/errors.py` | `5b1c6847813f` | Pending semantic review. |
| `backend/src/app/shared/observability/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `backend/src/app/shared/observability/domain.py` | `4be6daaf0f62` | Pending semantic review. |
| `backend/src/app/shared/observability/errors.py` | `a88b112c9f87` | Pending semantic review. |
| `backend/src/app/shared/observability/formatting.py` | `9bb646ab410b` | Pending semantic review. |
| `backend/src/app/shared/observability/lifecycle.py` | `7e68a9702da3` | Reviewed: frozen ASGI adapter, request-local closure state, bounded failure transport, rethrow of original BaseException, secondary delivery failure retained; awaits delegate native ASGI lifetime rather than external I/O. |
| `backend/src/app/shared/observability/policy.py` | `e323723f3171` | Pending semantic review. |
| `backend/src/app/shared/observability/requests.py` | `fd322cf1884c` | Pending semantic review. |
| `backend/src/app/shared/observability/schemas.py` | `c2bd8d7e94cc` | Pending semantic review. |
| `backend/src/app/shared/observability/services.py` | `b2a363ead406` | Pending semantic review. |
| `backend/src/app/shared/observability/sinks.py` | `d88c98db6900` | Pending semantic review. |
| `backend/src/app/shared/observability/tests/__init__.py` | `0bd51b497d66` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/shared/observability/tests/app_probe.py` | `65720d0ca9e8` | Pending semantic review. |
| `backend/src/app/shared/observability/tests/fakes.py` | `65f40f652aaa` | Pending semantic review. |
| `backend/src/app/shared/observability/tests/fixtures.py` | `9acfed4652a5` | Pending semantic review. |
| `backend/src/app/shared/observability/tests/lifecycle.py` | `747a33dcdd67` | Pending semantic review. |
| `backend/src/app/shared/observability/tests/requests.py` | `5f8a1b294d3c` | Pending semantic review. |
| `backend/src/app/shared/observability/tests/verify_http.py` | `9dbb5357811a` | Pending semantic review. |
| `backend/src/app/shared/observability/tests/verify_logs.py` | `c4c01b8e8959` | Pending semantic review. |
| `backend/src/app/shared/observability/util.py` | `a726d48b2cb7` | Pending semantic review. |
| `backend/src/app/shared/smoke.py` | `6aca1c758286` | Pending semantic review. |
| `backend/src/app/shared/tests/__init__.py` | `bb3c948c925e` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/shared/tests/entrypoints.py` | `7fa794d77107` | Pending semantic review. |
| `backend/src/app/shared/tests/fakes.py` | `67bf73843c47` | Pending semantic review. |
| `backend/src/app/shared/tests/migrations.py` | `ee59f171cdcc` | Pending semantic review. |
| `backend/src/app/shared/tests/python_rules.py` | `b1d328f47d4c` | Pending semantic review. |
| `backend/src/app/shared/tests/resources.py` | `14cd071167cc` | Pending semantic review. |
| `ml/src/ml/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/artifacts.py` | `b642c4a8106f` | Reviewed: frozen paths, synchronous persistence at explicit calls, validation before writes, installed Pipeline identity check; no payload diagnostics. ML role-layout disposition remains open. |
| `ml/src/ml/configuration.py` | `50cf964f707c` | Reviewed content: frozen options and fresh metric maps; ordered feature tuples preserve published column contracts. ML role-layout disposition remains open. |
| `ml/src/ml/domain.py` | `6133e37908c0` | Reviewed: immutable StrEnum split/metric identifiers; no I/O or state. |
| `ml/src/ml/errors.py` | `0f8351414e08` | Reviewed: dedicated typed exceptions; keyword constructors retain fields and construct messages; no resource effects. |
| `ml/src/ml/evaluation/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/evaluation/diagnostics.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/evaluation/evaluate_goalie_model.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/evaluation/evaluate_skater_model.py` | `bfa9affc880e` | Reviewed content: copied test-season frame, validated predictions, explicit artifact persistence and synchronous computation; no payload logs. Metric maps and mixed service/report/CLI layout remain open. |
| `ml/src/ml/evaluation/gate.py` | `45169694e280` | Reviewed content: finite whole temporal seasons, copied splits, guarded prediction shape, metadata policy raises at call site, baseline checks, resource-file context and no dotenv import. Repeated metric-map types and mixed role layout remain open. |
| `ml/src/ml/features/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/features/build_features.py` | `ff3cd819c223` | Reviewed content: copies caller frame, validates boundaries, preserves vector calculations, main owns diagnostics/exit and stdout report. CLI/service/helper role separation remains open. |
| `ml/src/ml/features/replacement_level.py` | `bdc973833297` | Reviewed content: owned options, controlled percentile, copied/merged frames, local mutable working sets, no hidden async or log-and-raise. CLI/service/helper role separation remains open. |
| `ml/src/ml/features/skater_features.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/observability/__init__.py` | `32b606a9a35d` | Reviewed: module docstring only; no executable behavior. |
| `ml/src/ml/observability/services.py` | `287ef3a17706` | Reviewed: no-context calls silent, explicitly passed invocation owns correlation, numeric aggregate mapping and lazy logging, no global mutable context or dataset/path serialization. |
| `ml/src/ml/paths.py` | `2752fb3a1c88` | Reviewed: explicit call-time path lookup, no import I/O; empty override intentionally selects source/wheel default; compatibility alias is a function. |
| `ml/src/ml/pipelines/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/pipelines/build_model_dataset.py` | `ca30e9808161` | Reviewed content: frozen forbidden-column set, explicit missing-frame acquisition, copy/validated many-to-one merge and leakage guards. Position mapping is repeated with feature construction; shared-policy/layout assessment remains open. |
| `ml/src/ml/pipelines/load_player_stats.py` | `947c848e1a93` | Reviewed content: immutable SQL, TOTAL-over-TEAM precedence, explicit connection injection and context-owned fallback resources, copy before filtering, main-owned diagnostics/stdout. Store/CLI/helper layout remains open. |
| `ml/src/ml/pipelines/load_salary_cap.py` | `bbb3ec3d19f0` | Reviewed content: fixed read-only SQL, context-owned fallback connection, copied query result and stdout-only reports; store/CLI/helper layout remains open. |
| `ml/src/ml/pipelines/run_pipeline.py` | `217d9a56aca4` | Reviewed content: frozen CLI options, parse/validate before resources, one owned connection for missing inputs, no mutation of injected frames, error report returns exit code. Role layout remains open. |
| `ml/src/ml/policy.py` | `010d9688c34b` | Reviewed: frozen policies read their fields and return violations; callers own raising; metadata decision order retained. |
| `ml/src/ml/schemas.py` | `09b98a46482c` | Reviewed content: frozen Pydantic metadata, constrained aliases, frame/options boundary validation and finite/grain guards. Boundary-policy and role-layout disposition remains open. |
| `ml/src/ml/tests/__init__.py` | `4d67111bded2` | Reviewed: module docstring only; no executable behavior. |
| `ml/src/ml/tests/fakes.py` | `11f1c32871c8` | Pending semantic review. |
| `ml/src/ml/tests/fixtures.py` | `5ebabcbb1ac1` | Pending semantic review. |
| `ml/src/ml/tests/strategies.py` | `5f53ce3abcbb` | Pending semantic review. |
| `ml/src/ml/training/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/training/train_goalie_value.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/training/train_skater_value.py` | `8296f2b575a5` | Reviewed content: copied temporal target frames, owned fitted sklearn resources, frozen result/metadata, explicit artifact adapter, aggregate diagnostics and main-owned exit. Domain/service/CLI placement and metric-map aliases remain open. |
| `ml/src/ml/valuation/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/valuation/cap_allocation.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/valuation/fair_cap_hit.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/valuation/surplus_value.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `tests/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `tests/backend/__init__.py` | `5c6f62d24e39` | Reviewed: module docstring only; no executable behavior. |
| `tests/backend/conftest.py` | `57e1ff60d75a` | Pending semantic review. |
| `tests/backend/test_alembic_logging.py` | `2366bc184922` | Pending semantic review. |
| `tests/backend/test_api.py` | `5ce9433e0198` | Pending semantic review. |
| `tests/backend/test_api_logging.py` | `e3a420fe55f8` | Pending semantic review. |
| `tests/backend/test_api_service.py` | `b18fd6ca5d34` | Pending semantic review. |
| `tests/backend/test_capspace.py` | `aaf46338a807` | Pending semantic review. |
| `tests/backend/test_capspace_postgres_integration.py` | `fc816dd7ade8` | Pending semantic review. |
| `tests/backend/test_cli_contracts.py` | `93090bedf255` | Pending semantic review. |
| `tests/backend/test_command_cancellation.py` | `a67078ec6e12` | Pending semantic review. |
| `tests/backend/test_command_logging.py` | `4a1ee6437e7f` | Pending semantic review. |
| `tests/backend/test_config.py` | `7624d1154587` | Pending semantic review. |
| `tests/backend/test_container_smoke.py` | `b24d41512eaf` | Pending semantic review. |
| `tests/backend/test_contract_domain.py` | `a992295230c4` | Pending semantic review. |
| `tests/backend/test_contract_lifecycle.py` | `ff97b7834779` | Pending semantic review. |
| `tests/backend/test_contract_lifecycle_postgres.py` | `820899fbe154` | Pending semantic review. |
| `tests/backend/test_contract_parsing.py` | `3a3ca5de4c15` | Pending semantic review. |
| `tests/backend/test_database_cleanup.py` | `435602cf81d6` | Pending semantic review. |
| `tests/backend/test_database_transactions.py` | `2c682bdcfe33` | Pending semantic review. |
| `tests/backend/test_historical_options.py` | `6b5661805392` | Pending semantic review. |
| `tests/backend/test_ingestion.py` | `f2c145032c20` | Pending semantic review. |
| `tests/backend/test_ingestion_logging.py` | `56c6d291e880` | Pending semantic review. |
| `tests/backend/test_lifecycle_logging.py` | `d633f2599aa3` | Pending semantic review. |
| `tests/backend/test_logging_policy.py` | `6bccec5bccd4` | Pending semantic review. |
| `tests/backend/test_logging_startup.py` | `762d56384b27` | Pending semantic review. |
| `tests/backend/test_migration_tooling.py` | `33e29174d135` | Pending semantic review. |
| `tests/backend/test_openapi_contract.py` | `205f0a706841` | Pending semantic review. |
| `tests/backend/test_operational_errors.py` | `001eb514484d` | Pending semantic review. |
| `tests/backend/test_postgres_integration.py` | `3a35639dcdc6` | Pending semantic review. |
| `tests/backend/test_python_rules.py` | `e5fab98155b0` | Pending semantic review. |
| `tests/backend/test_request_logging.py` | `ccb2eee7cab7` | Pending semantic review. |
| `tests/backend/test_roster_status_service.py` | `f21e6de8469b` | Pending semantic review. |
| `tests/backend/test_runtime_resources.py` | `2c135b804ce4` | Pending semantic review. |
| `tests/backend/test_source_identity.py` | `fe3873e02c25` | Pending semantic review. |
| `tests/backend/test_source_identity_postgres.py` | `d4c5cd014abc` | Pending semantic review. |
| `tests/backend/test_source_ingestion.py` | `993c86ed1e8d` | Pending semantic review. |
| `tests/backend/test_supported_entrypoints.py` | `5fd5eba60222` | Pending semantic review. |
| `tests/backend/test_transaction_logging.py` | `b57666912f9e` | Pending semantic review. |
| `tests/conftest.py` | `2084ef23201a` | Pending semantic review. |
| `tests/ml/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `tests/ml/conftest.py` | `3a7bc20eebd4` | Pending semantic review. |
| `tests/ml/test_boundaries.py` | `751135e90cc5` | Pending semantic review. |
| `tests/ml/test_features.py` | `6ab99d4f5ea2` | Pending semantic review. |
| `tests/ml/test_logging.py` | `ac7c5f639499` | Pending semantic review. |
| `tests/ml/test_metadata.py` | `d29807141a1a` | Pending semantic review. |
| `tests/ml/test_paths.py` | `f3fb2d5bd22e` | Pending semantic review. |
| `tests/ml/test_valuation.py` | `f1f5ced5409e` | Pending semantic review. |

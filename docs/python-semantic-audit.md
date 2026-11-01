# Python semantic audit checkpoint

This is an incomplete file-by-file review, not phase-7 acceptance. Scope is all
237 tracked/new Python files in the acceptance worktree based on `4727840`. Source
digests identify exactly what was inspected; changed files require re-review.
Generated artifacts, environments and retired `.py.txt` loaders are not source
entries. The structural gate separately checks all supported executable roots.

Read `~/.codex/python-guidelines.md` before this review. Mechanical lint, format,
type, structural, test and package results do not waive semantic decisions.
18 empty files and 20 module-docstring-only package files have no executable
behavior to assess. 69 other files have received the content review
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

## ML findings resolved in this checkpoint

- Canonical frozen configuration and artifact-path values now live in domain.py.
  Legacy configuration/artifact imports are explicit compatibility boundaries.
- Feature, dataset, training and evaluation orchestration use services.py; pure
  helpers use util.py; database/artifact/metadata adapters use repository.py.
  Established command modules own parsing, stdout reports and main-only logging.
- One MetricValues alias preserves the public string-key metric API. Metric
  identifiers still control the internal comparison traversal. One enum-derived
  mapping owns skater position grouping in both dataset and feature paths.
- The dataset reader is a minimal runtime-checkable Protocol. A frozen SQL adapter
  borrows its connection; its context factory owns resources. Missing inputs share
  one connection, injected readers retain caller ownership, and preloaded frames
  do not trigger reads. Tests include a falsy reader and input preservation.
- Test columns are immutable; arrays are created in fixtures instead of shared
  decorator data. Invalid-frame arrangement now belongs to fixtures.
- Source comparison confirms 22 moved function bodies, nine CLI main/parser
  bodies, argparse metadata and both SQL literals retain their prior behavior.
  Shared grouping and connection ownership changes have dedicated regressions.

## Cleanup findings resolved in this checkpoint

- Note rendering and attachment are best-effort, independent from secondary
  failure metadata. The resource owner still rethrows the original failure or
  cancellation; annotation faults cannot interrupt the remaining cleanup.
- Caught HTTP error responses are explicitly closed. A read failure remains
  primary if close also fails. Native status/text conversion and successful
  response context behavior remain unchanged.
- Regressions failed in 26 cases before the fix, then passed with original
  error/cancellation identity, cleanup order and secret-free bounded output.

## Findings requiring resolution

- Carry the existing frozen PlayerQuery from the route into the service instead
  of threading ten positional parameters before constructing it.
- Finish boundary-specific decisions about API response-model mutability,
  summary query options and the remaining naming/layout judgments.

Required framework and historical-migration dispositions above remain open.
Do not rewrite frozen history or introduce a global-state approximation.
The 130 remaining nonempty files still require complete semantic review;
passing mechanical and behavior gates does not accept them implicitly.

## File ledger

| Source | SHA-256 prefix | Review disposition |
| --- | --- | --- |
| `backend/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `backend/database/backfill_team_stints.py` | `8cd7c439de15` | Reviewed: frozen command options and ordered bounds, main-owned diagnostics, explicit commit/dry-run rollback, BaseException compensation and close preserving primary failure; core backfill logic delegated. |
| `backend/database/container_smoke.py` | `b6dc16038c68` | Reviewed/fixed: typed response contract, bounded readiness and explicit caught-HTTPError close. Read failure/cancellation remains primary when close also fails; status/raw-text conversion is unchanged. Native success contexts are verified closed. |
| `backend/database/migration_preflight.py` | `4307aec8a137` | Reviewed: explicit operational URL resolver, fixed catalog queries, connection context and engine cleanup, report values kept distinct from command exit ownership; no import-time resources. |
| `backend/database/migration_smoke.py` | `64354d6e86c8` | Reviewed: fixed reference-data contract and shared payload predicates, context-owned database/TestClient lifetimes, original status/body failures preserved, main-owned logging and fixed stdout PASS lines. |
| `backend/database/migrations/__init__.py` | `efbca4488e57` | Reviewed: module docstring only; no executable behavior. |
| `backend/database/migrations/domain.py` | `2b175b1007fe` | Reviewed: frozen invocation options separate CLI/programmatic and offline/online ownership. |
| `backend/database/migrations/services.py` | `8c2d8f85c21a` | Reviewed: immutable progress callback, NullPool and bounded SQL options, connection/transaction contexts and cleanup preserving original failure; main owns logging, programmatic branch raises without error report. Alembic load boundary remains open. |
| `backend/database/migrations/util.py` | `fdd2ee713f6f` | Reviewed: locally owned controlled dispatch table, typed configuration fields, no exception text copying or import I/O. |
| `backend/database/schema_snapshot.py` | `614a2d92fa7a` | Reviewed: named catalog type, local fixed query table, context-owned connection and guaranteed engine disposal, deterministic snapshot rendering, frozen command options and explicit output/update ownership. |
| `backend/database/verify_migrations.py` | `e2c57a5e94bd` | Reviewed: report collection over native Alembic history, explicit path conversion, frozen command options, main-owned diagnostics/status and no import-time history reads. Compatibility alias retained. |
| `backend/database/verify_python_rules.py` | `dac613daa2be` | Reviewed: immutable rule IDs/findings, typed scope failure, pure AST classification, explicit root traversal without imports, fail-closed scope, main-owned lazy diagnostics and deterministic exits. Manual scope limits remain documented. |
| `backend/export_openapi.py` | `ea0f876c2f0c` | Reviewed: schema-only construction with no database/dotenv, deterministic serialization, frozen options and explicit check/write paths; main owns diagnostics. Private schema helper naming remains a small manual naming decision. |
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
| `backend/src/app/api/domain.py` | `207f93061887` | Reviewed content: frozen database rows/query/page values, tuple row snapshots and structural response mapping types. Mapping outputs are per-response values, not shared mutable domain state; published field names and nullability remain unchanged. |
| `backend/src/app/api/errors.py` | `bd34cb531625` | Reviewed: dedicated typed failures retain IDs/seasons and public HTTP envelopes. Common exception inheritance supplies the framework handler contract; exception mutability is native traceback/annotation behavior, not reusable application state. |
| `backend/src/app/api/policy.py` | `8f799d93d8d1` | Reviewed: pure historical cents/season calculation, local immutable threshold data and guarded next selection; no I/O or module mutable state. Fixed published policy values are not logging/environment tunables. |
| `backend/src/app/api/queries.py` | `eb3a586b0e03` | Reviewed: immutable fixed SQL definitions only; named binds, explicit TOTAL/team-stint precedence, stable ordering, season visibility and existing cap/model selection policy. No execution or mutable import state. |
| `backend/src/app/api/repository.py` | `4da8ed6f725d` | Reviewed: minimal consumer-complete runtime-checkable read Protocol, frozen borrowed session adapter, validated frozen rows, bound values and controlled sort/filter fragments; no resource ownership or logging at import. Summary selection option grouping remains a manual design item. |
| `backend/src/app/api/routes.py` | `26d73f2e592a` | Reviewed content: router created explicitly, named Annotated aliases, per-request context-owned session and synchronous database routes, controlled validation translation. PlayerQuery handoff should replace the current long positional service call. |
| `backend/src/app/api/schemas.py` | `d7fbc367ffcc` | Reviewed content: native Pydantic boundary models, forbidden extras and fixed wire enums/field names. Explicit enum strings preserve the public contract; response-model mutability is a boundary-specific disposition still to record. |
| `backend/src/app/api/service.py` | `b510a125fdce` | Reviewed content: frozen injected repository/date ownership, explicit season/identity guards, fresh response aggregates and bounded loop nesting. Finding: players still threads ten arguments before constructing the existing PlayerQuery; move that value boundary outward. |
| `backend/src/app/api/tests/__init__.py` | `89699d68cd40` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/api/tests/fakes.py` | `465becfe754e` | Pending semantic review. |
| `backend/src/app/api/tests/fixtures.py` | `8bbfa684ad4a` | Pending semantic review. |
| `backend/src/app/api/util.py` | `f9144c0881f3` | Reviewed: pure conversion into fresh response maps, explicit nullable fields, owned ranking list and stable ID tiebreak; no mutation of frozen repository rows or external effects. |
| `backend/src/app/config.py` | `2e25f8385208` | Reviewed: frozen settings/snapshot, explicit call-time dotenv merge with exports winning, narrow environment selection, typed validation, no import-time external resources. |
| `backend/src/app/database.py` | `bf1fa2396edb` | Reviewed: frozen engine/session dependencies, explicit construction and rollback/dispose/close contexts, original BaseException/cancellation retained, transaction diagnostics follow actual DB outcomes, and minimal runtime-checkable transaction factory. |
| `backend/src/app/main.py` | `5aa95f0094bf` | Reviewed content: native FastAPI extension owns middleware/schema, settings captured at factory, resources owned by lifespan, bounded threaded disposal preserves primary failure. Framework inheritance and approved logging hook are explicit; export/import boundary remains open. |
| `backend/src/app/shared/__init__.py` | `e27164e808fc` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/shared/calendar.py` | `91d7d52a9526` | Reviewed: pure date-derived July-1 boundary and compatibility function alias; no state or I/O. |
| `backend/src/app/shared/cleanup.py` | `c71230c7da56` | Reviewed/fixed: best-effort note rendering and attachment cannot replace a pending primary or stop later cleanup. Native notes remain for ordinary errors; bounded secondary metadata is independent. Annotation guards preserve original cancellation/interrupt propagation by the resource owner. |
| `backend/src/app/shared/cli.py` | `321790265705` | Reviewed: published numeric exit contract is explicit IntEnum values, not tunable ordinals; structured keyword argument error stores its fields. No state/I/O. |
| `backend/src/app/shared/environment.py` | `46b0dac87bab` | Reviewed: explicit operational URL resolver, no dotenv or import I/O, deliberate missing/empty distinction, controlled configuration failures and compatibility function aliases. |
| `backend/src/app/shared/errors.py` | `5b1c6847813f` | Reviewed: dedicated missing-schema failure with typed table field and controlled migration guidance; exception constructor only. |
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
| `backend/src/app/shared/smoke.py` | `6aca1c758286` | Reviewed: shared explicit payload predicates and typed operational exception fields; raw response/body values are failure data, not emitted diagnostic fields. No transport effects or state. |
| `backend/src/app/shared/tests/__init__.py` | `bb3c948c925e` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/shared/tests/entrypoints.py` | `7fa794d77107` | Pending semantic review. |
| `backend/src/app/shared/tests/fakes.py` | `67bf73843c47` | Pending semantic review. |
| `backend/src/app/shared/tests/migrations.py` | `ee59f171cdcc` | Pending semantic review. |
| `backend/src/app/shared/tests/python_rules.py` | `b1d328f47d4c` | Pending semantic review. |
| `backend/src/app/shared/tests/resources.py` | `639123a9c76b` | Reviewed: frozen scenario holders distinguish owned probe lists and borrowed handles from immutable value snapshots; native HTTP bodies are fixture-owned, teardown closes buffers, and database probe behavior remains explicit. |
| `ml/src/ml/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/artifacts.py` | `4243f83c055c` | Reviewed: explicit compatibility exports of domain paths and repository functions only; no persistence at import. |
| `ml/src/ml/configuration.py` | `3686072e3086` | Reviewed: explicit compatibility exports of canonical domain values only; old configuration import paths remain available without duplicate state. |
| `ml/src/ml/domain.py` | `2b835e60de10` | Reviewed: canonical frozen options/artifact paths, immutable ordered column contracts, enum identifiers and metric-map alias; no mutable import state or I/O. Position identity maps to a controlled group property. |
| `ml/src/ml/errors.py` | `0f8351414e08` | Reviewed: dedicated typed exceptions; keyword constructors retain fields and construct messages; no resource effects. |
| `ml/src/ml/evaluation/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/evaluation/diagnostics.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/evaluation/evaluate_goalie_model.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/evaluation/evaluate_skater_model.py` | `9457c022a79c` | Reviewed: CLI/stdout and artifact-path boundary, metric/function aliases preserved; parser/main and argparse module-docstring metadata match the prior command. |
| `ml/src/ml/evaluation/gate.py` | `ff426acd4b3f` | Reviewed: committed resource selection, fixed acceptance baseline and main-owned diagnostics; helper exports and original help metadata retained, pure helpers/read adapter moved to role files. |
| `ml/src/ml/evaluation/repository.py` | `55601cb74f33` | Reviewed: explicitly selected metadata file owned by context manager, then validated through the pure metadata boundary; function body unchanged. |
| `ml/src/ml/evaluation/services.py` | `309e64930055` | Reviewed: copied evaluation frame, validated prediction shape, explicit artifact adapter and aggregate metrics. Three moved function bodies unchanged; no copied CLI/report definitions remain. |
| `ml/src/ml/evaluation/util.py` | `6203c7428e4d` | Reviewed: pure finite temporal splits, prediction shape/clipping, metadata validation and metric checks; alias retains published string-key API, enum controls metric traversal. Five moved bodies unchanged. |
| `ml/src/ml/features/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/features/build_features.py` | `eaba815f2fc8` | Reviewed: command/stdout boundary with explicit compatibility exports; parser/main bodies unchanged, logging configured only in main, diagnostics return exits without rethrow. |
| `ml/src/ml/features/replacement_level.py` | `7ec2635b0da9` | Reviewed: command/stdout boundary, effective-percentile report and legacy exports; parser/main and calculation bodies preserved through service extraction. |
| `ml/src/ml/features/services.py` | `db912b834ef8` | Reviewed: dataframe-copy ownership, validation before calculation, source fallback through dataset service, guarded rates/eligibility and season-position replacement isolation. No CLI setup or reporting. |
| `ml/src/ml/features/skater_features.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/features/util.py` | `b9a411c6d87b` | Reviewed: pure per-60 arithmetic and one enum-derived position mapping; source-code spelling preserved, unknown/null codes stay null, row index retained and inputs unmodified. |
| `ml/src/ml/observability/__init__.py` | `32b606a9a35d` | Reviewed: module docstring only; no executable behavior. |
| `ml/src/ml/observability/services.py` | `287ef3a17706` | Reviewed: no-context calls silent, explicitly passed invocation owns correlation, numeric aggregate mapping and lazy logging, no global mutable context or dataset/path serialization. |
| `ml/src/ml/paths.py` | `2752fb3a1c88` | Reviewed: explicit call-time path lookup, no import I/O; empty override intentionally selects source/wheel default; compatibility alias is a function. |
| `ml/src/ml/pipelines/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/pipelines/build_model_dataset.py` | `415669da04c1` | Reviewed: command/stdout boundary and public dataset/forbidden-column exports; main/parser preserved and transformation/resource ownership moved to service/repository roles. |
| `ml/src/ml/pipelines/load_player_stats.py` | `f9ff392f13c3` | Reviewed: command/stdout boundary and public loader/query re-exports; main/parser, loader body and SQL literal preserved. |
| `ml/src/ml/pipelines/load_salary_cap.py` | `5a9a84f46ec9` | Reviewed: command/stdout boundary and public loader/query re-exports; main/parser, loader body and SQL literal preserved. |
| `ml/src/ml/pipelines/repository.py` | `168f778693ce` | Reviewed: fixed SQL literals unchanged, explicit borrowed connections, guarded standalone resource scopes, minimal runtime-checkable reader Protocol and frozen SQL adapter; context factory owns engine/connection cleanup. |
| `ml/src/ml/pipelines/run_pipeline.py` | `bdd0a144e959` | Reviewed: frozen CLI options, validation before resources, public pipeline compatibility and unchanged parser/main; shared reader orchestration resides in services. |
| `ml/src/ml/pipelines/services.py` | `6824133d52a0` | Reviewed: validate options before acquisition; injected reader distinguished from None, preloaded frames retained, missing inputs share one context-owned reader, pure assembly copies frames and enforces grain/leakage. No raw data diagnostics. |
| `ml/src/ml/policy.py` | `6c7f532ae6fc` | Reviewed: frozen policies read canonical domain values, return typed violations and retain decision order; no resource effects. |
| `ml/src/ml/repository.py` | `a8c969308ebc` | Reviewed: explicit model/metadata/CSV persistence, validate before writing, context-owned metadata file reads, sklearn Pipeline guard and aggregate diagnostics. Moved function bodies verified unchanged. |
| `ml/src/ml/schemas.py` | `e066b47887cd` | Reviewed: frozen Pydantic metadata, constrained aliases and explicit frame/options boundary validation; canonical domain imports replace compatibility-layer dependency. |
| `ml/src/ml/tests/__init__.py` | `4d67111bded2` | Reviewed: module docstring only; no executable behavior. |
| `ml/src/ml/tests/fakes.py` | `7b6b69f8c103` | Reviewed: frozen fixtures hold borrowed resources and frames; call lists are intentionally fixture-owned observation probes, not shared domain values. Falsy reader exercise catches accidental truthiness replacement. |
| `ml/src/ml/tests/fixtures.py` | `2d449ca1f3d4` | Reviewed: function-scoped scenario generation, local mutable construction and named row alias; no shared dataframe construction or external I/O at import. |
| `ml/src/ml/tests/strategies.py` | `5f53ce3abcbb` | Pending semantic review. |
| `ml/src/ml/training/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/training/domain.py` | `e46a3b25b6e1` | Reviewed: frozen result separates fitted mutable sklearn resource ownership from immutable metadata; metadata properties return fresh serialized snapshots. No resource effects at construction. |
| `ml/src/ml/training/services.py` | `b135e78b3535` | Reviewed: copied temporal targets, owned fitted sklearn pipelines, explicit options and artifact adapter, aggregate diagnostics; all five moved calculation bodies verified unchanged. |
| `ml/src/ml/training/train_goalie_value.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `ml/src/ml/training/train_skater_value.py` | `fc330df0e81e` | Reviewed: CLI artifact-path selection and unchanged parser/main; explicit exports retain training functions, result type, feature constants and train/evaluate aliases. |
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
| `tests/backend/test_container_smoke.py` | `02fdc5a44940` | Reviewed: native HTTPError/BytesIO fixtures cover handled status, invalid bytes, read/close failures, cancellation, interruption and successful/decode-failed responses; no real network. Readiness and contract specimens are read-only, observations are fixture-owned. |
| `tests/backend/test_contract_domain.py` | `a992295230c4` | Pending semantic review. |
| `tests/backend/test_contract_lifecycle.py` | `ff97b7834779` | Pending semantic review. |
| `tests/backend/test_contract_lifecycle_postgres.py` | `820899fbe154` | Pending semantic review. |
| `tests/backend/test_contract_parsing.py` | `3a3ca5de4c15` | Pending semantic review. |
| `tests/backend/test_database_cleanup.py` | `6cd3fbacf88d` | Reviewed: fixture-scoped typed failures/probes and original-cause checks; hostile repr, overridden annotation and invalid native notes cannot mask primary or skip close. Both formats omit secrets and retain bounded secondary diagnostics. |
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
| `tests/ml/test_boundaries.py` | `5d4dfa12759d` | Reviewed: fixtures own settings/resources/arrays and immutable class column metadata; borrowed/preloaded reader tests, snapshot mutation and artifact round trips preserve input ownership. Arrangement removed from invalid-shape acts; normal imports replace inline module discovery. |
| `tests/ml/test_features.py` | `fcf5144a399d` | Reviewed: fixture-owned scenarios, named percentile regressions, independent position-code contract, input/index preservation and meaningful numerical/grain/leakage assertions. No external resources. |
| `tests/ml/test_logging.py` | `ac7c5f639499` | Pending semantic review. |
| `tests/ml/test_metadata.py` | `d29807141a1a` | Pending semantic review. |
| `tests/ml/test_paths.py` | `f3fb2d5bd22e` | Pending semantic review. |
| `tests/ml/test_valuation.py` | `f1f5ced5409e` | Pending semantic review. |

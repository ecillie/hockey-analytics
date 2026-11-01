# Python semantic audit checkpoint

This is an incomplete file-by-file review, not phase-7 acceptance. Scope is all
237 tracked/new Python files in the acceptance worktree, with source digests
updated after `02d161a`. Digests identify exactly what was inspected; changed
files require re-review.
Generated artifacts, environments and retired `.py.txt` loaders are not source
entries. The structural gate separately checks all supported executable roots.

Read `~/.codex/python-guidelines.md` before this review. Mechanical lint, format,
type, structural, test and package results do not waive semantic decisions.
18 empty files and 20 module-docstring-only package files have no executable
behavior to assess. 132 other files have received the content review
recorded below; unresolved layout/boundary decisions are explicit. Every other
nonempty file remains pending.

Open release decisions include Vercel's exported ASGI application, Alembic's
framework-executed bootstrap, intentional source-only failing test doubles,
legacy contract role-file layout, and frozen historical migration compatibility.
The previously approved API lifespan logging hook is the only recorded owner
approval; this ledger creates no additional blanket exception.

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

- PlayerQuery handoff and immutable summary-selection options are resolved.
  HTTP/OpenAPI fields, sort allowlists and bound values remain unchanged.
- Native API/source-document Pydantic objects remain per-call validation and
  serialization buffers. Their nested lists/dicts/parse trees are owned locally;
  freezing only the model shell would not make those graphs immutable. Immutable
  domain rows/contracts and source snapshots remain the cross-layer boundary.
  This is a specific ownership disposition, not a general mutable-value waiver.
- Contract zero-coverage handling and shared injected worker bounds are resolved.
  Remaining legacy role-file and broad SQL tuple/naming judgments stay open.
- ScheduleDay aliasing, durable boolean/negative counts, CSV file-adapter placement
  and broad stat-kind selection are resolved in the source-boundary checkpoint.
  Valid legacy stat-kind strings and regular-season filtering remain compatible.
- Remaining findings include primary-preserving cursor/error-response ownership in
  team-stint and cached-summary readers and the roster HTTP adapter; move roster
  fetch_validated out of pure utilities and group classification evidence as an
  immutable per-sync value. Native Pydantic validator ValueErrors and remaining
  option/error/helper role placements still need their exact disposition.

## Diagnostic snapshot and worker findings resolved

DiagnosticCollection now retains frozen frame/exception models and immutable
nested tuples. Only explicit serialization creates mutable copies. Mutation and
copy-isolation regressions protect this guarantee. Best-effort dictionary
metadata guards cover BaseException at attribute access only; application work,
native cancellation/interrupt and sink delivery retain their existing ownership.
Request, host-filter, formatter and real lifespan regressions preserve the
primary and bounded secret-free output when metadata itself raises an error,
cancellation or interrupt. The native attribute-fault double is intentionally
throwing source-only test support; a returned policy value cannot reproduce it.

One WorkerLimitPolicy owns bounds at validation and execution. A custom limit
accepted by HistoricalContractService now reaches ProfileFetcher; invalid direct
worker counts open no sessions, and concurrent owned sessions all close. The
existing public worker argument and default limit remain compatible.

Required framework and historical-migration dispositions above remain open.
Do not rewrite frozen history or introduce a global-state approximation.
The 67 remaining nonempty files still require complete semantic review;
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
| `backend/src/app/ScriptingFiles/FullDataScript/capspace.py` | `c71c23f20821` | Reviewed content: compatibility exports/defaults derive from frozen options; established public keyword APIs assemble the options boundary. Injected session/repository factories preserve caller ownership. Main converts Namespace immediately, owns logging/status and prints only the report. Existing command/module layout is retained for compatibility; remaining role-file disposition is explicit. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/__init__.py` | `78dc82a8112a` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/active_repository.py` | `d34803063d7f` | Reviewed content: consumer-complete runtime Protocol, frozen borrowed cursor adapter and transaction-owned factory. SQL values are bound; local mutable name indexes/counters belong to one save operation. Native Json values are created at the persistence edge. Write-context role/narrow-type decisions remain part of the final layout disposition. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/active_services.py` | `9a5c6bc667fd` | Reviewed: frozen injected factories/context; native session contexts bound each synchronous HTTP request. ThreadPoolExecutor joins all work before snapshot validation; only transport failures become failed profiles. Coverage policy runs before opening the write transaction, and progress emits bounded counts. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/domain.py` | `29a4813a9d8f` | Reviewed: frozen tuple-backed contract/profile outcomes and enum-derived status/coverage. Stored JSON strings isolate source snapshots; source_payload decodes a fresh mutable copy on each access. No resources or mutable application state at import. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/errors.py` | `427b82d3ef9b` | Reviewed/fixed: typed ContractOptionError now has its canonical errors role while options retains its public compatibility export. Marker exception hierarchy groups typed parsing/reconciliation leaves; persisted source details are never copied into runtime logs. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/http.py` | `13604ee9a789` | Reviewed: minimal runtime Protocols, bounded synchronous native requests/retries, context-owned sessions and explicit borrowed factories. Locks serialize borrowed-session calls; eager native responses release transport connections. Guarded slug traversal has explicit termination, identity-validated fallback and bounded progress fields. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/options.py` | `e202c922cf52` | Reviewed/fixed: frozen injectable options and typed validation returns. Worker bounds delegate to one WorkerLimitPolicy; the previous exception import remains compatible. Finite HTTP limits and ordered ranges remain enforced. Remaining domain/policy role placement is explicit. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/policy.py` | `fd5ff73f5bbb` | Reviewed/fixed: one WorkerLimitPolicy now owns the historical worker invariant used by validation and fetch execution. Conservative identity matching and reconciliation still return typed violations and fail closed on conflicting identity; no I/O. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/reporting.py` | `776416f2c542` | Reviewed content: fresh persisted profile snapshots, local source grouping and materialized one-pass metrics; no runtime log payload copies. Pure reporting helpers currently occupy a descriptive legacy role file; final layout disposition remains open. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/repository.py` | `8dcd6fd0a10e` | Reviewed/fixed: coverage percentage explicitly distinguishes zero rows. Bound SQL, immutable mapping-proxy context snapshots, conflict-preserving reconciliation and context-owned transactions remain unchanged. Pending inserts/counters are local; broad heterogeneous SQL tuples and remaining role placement need final disposition. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/schemas/__init__.py` | `8c25f29beb35` | Reviewed: explicit public document imports and established tag helper aliases; dependencies now inspected. No I/O or mutable application state at import. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/schemas/active.py` | `da783f50d133` | Reviewed: source-boundary parsing validates index/profile shape and slug, minimum row coverage, native date conversion and contiguous seasons. Empty/duplicate seasons fail in parse_mapping_contract before min/index operations. Parsed contracts leave the boundary as frozen values. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/schemas/contracts.py` | `9c133d82d1a6` | Reviewed: boundary-only JSON/table parsing, explicit null/empty distinction, finite payload traversal and typed parse failures. Source identity and nonempty/unique season guards precede normalization; immutable domain snapshots isolate native parser mappings. No I/O/logging. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/schemas/documents.py` | `b8e438d701ac` | Reviewed content: Pydantic validates external JSON and native BeautifulSoup owns the parse tree. SourceDocument is a newly owned boundary buffer, not shared/frozen domain state; fresh page decoding and explicit text/attribute narrowing. Boundary mutability disposition applies. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/schemas/serialization.py` | `d48fc2cec40c` | Reviewed: asdict creates independent persistence snapshots, internal JSON-string fields are removed, decoded public payloads and season serialization preserve the stored compatibility shape. No I/O or leaked mutable domain state. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/services.py` | `3eafb140feee` | Reviewed/fixed: fetch execution receives the same injected worker limits validated by the service, with default direct-call compatibility retained. Joined workers close owned sessions; invalid direct worker counts open none. Batch commit/progress/cause semantics remain unchanged; role placement remains open. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/__init__.py` | `0e8f75076203` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/fakes.py` | `62e5ed9001dc` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/fixtures.py` | `652dc45a4982` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/postgres.py` | `bc3b22c935c8` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/strategies.py` | `a569707f457d` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/transport.py` | `3d51b48414a0` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/util.py` | `ad4626e15580` | Reviewed: pure money/season/text/date conversion with typed boundary failures and explicit missing values. Decimal rounding remains source-selected; nonfinite/negative/unrepresentable money is rejected. Snapshot decoding returns a fresh value; no resources or import-time I/O. |
| `backend/src/app/ScriptingFiles/FullDataScript/ingestion.py` | `6dd0ad2ac04b` | Reviewed content: compatibility entrypoints assemble frozen options and injected native adapters only on invocation, preserve borrowed resource ownership, and track durable runs separately from transactions. Invalid stat-kind strings now fail with a typed cause. Last-good fallbacks produce warning counts and parent-owned terminal errors; session cleanup preserves primary failures. Finding: cached CapWages summary manually closes its cursor only after successful fetch; move it under explicit failure-preserving ownership and finish role placement. |
| `backend/src/app/ScriptingFiles/FullDataScript/ingestion_tracking.py` | `17f8a92976a5` | Reviewed content: runtime-checkable named callable Protocol preserves decorator signatures and native metadata; invocation-time run context owns resources, immutable run identity is passed to workers and translated failures are rethrown once. Failure-reporting errors attach best-effort to the primary; stored summaries remain distinct from safe log counts. Concrete run typing/compatibility role remains a final seam disposition. |
| `backend/src/app/ScriptingFiles/FullDataScript/populate_roster_status.py` | `5c7d1f03acbf` | Reviewed: legacy native command boundary builds injected feed/repository services only during invocation, uses explicit None checks, and rolls back incomplete feeds before returning. Main owns logging/hook/exit codes and one report; no Namespace escapes its zero-option parser. Established wire names and asdict summary shape are retained. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/__init__.py` | `e0395eee5ae5` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/ahl_roster_service.py` | `135c28d3585f` | Reviewed: frozen injected client/options; native schema validation, explicit season resolution and per-team bounded transport attempts produce immutable complete/partial results. Conflicting external identities fail closed; no logging, import I/O or shared mutable buffers. Existing descriptive service-module path remains compatible. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/domain.py` | `0e829827ae62` | Reviewed: frozen scalar/tuple roster identities/results/summary and injectable HTTP/feed options. Database status values derive from enum names, preserving uppercase wire values while using auto internally. Completeness derives from immutable error tuples; no import-time resources. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/errors.py` | `fcad4786f075` | Reviewed: typed JSON, feed and incomplete-sync failures build messages and retain structured context. Source reasons belong to reports/persistence and are not copied by the runtime formatter. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/http_json_client.py` | `f8d5cfef77c5` | Reviewed content: minimal runtime JsonClient, frozen HTTP options and native bounded urlopen context; JSON/JSONP is validated without eval and typed decode errors retain their cause. Finding: raised HTTPError owns an unclosed response; explicitly close caught error responses while preserving the primary failure. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/nhl_roster_service.py` | `373a402fe733` | Reviewed: frozen injected client/feed options; validated sorted team traversal produces immutable roster/error tuples and preserves incomplete feeds. Source transport failures translate once, with no logger ownership or import-time I/O. Existing descriptive service-module path remains compatible. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/policy.py` | `df96de96ad2c` | Reviewed content: LTIR/active/minors/unknown precedence is conservative on incomplete feeds and consumes only supplied evidence. Finding: six related evidence parameters should become one immutable per-sync value; only membership keys of ahl_matches are required. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/repository.py` | `efa87742796e` | Reviewed: minimal runtime repository Protocol and frozen borrowed connection adapter. Native cursor contexts close each fixed/bound query/write, immutable rows/status sets leave persistence, and outer transaction ownership remains with the sync entrypoint. Empty batches do no I/O and source IDs are preserved conservatively. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/schemas.py` | `3e4461105b5f` | Reviewed: frozen native Pydantic scalar/tuple boundary graphs and strict named feed-ID aliases. Defaults are immutable or native factories; permissive source fields stay at the external shape boundary. No resources or mutable application state at import. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/services.py` | `cf332c14f50c` | Reviewed content: frozen injected feeds/repository/context, read-only evidence gathering and safe count events precede local decisions and transaction-owned writes. Final caller rejects incomplete summaries and rolls back. Finding: classification evidence threads six parameters and should be grouped immutably without retaining the mutable match dictionary. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/tests/__init__.py` | `ec5000bdb273` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/tests/fakes.py` | `7b5dea773a5e` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/tests/fixtures.py` | `b9523d20a965` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/util.py` | `335e1bc4e70f` | Reviewed content: immutable identity matching inputs and local indexes fail closed on duplicate/conflicting IDs and ambiguous names/birth dates. Pure parsers normalize source models. Finding: fetch_validated performs transport I/O in the utility role; move it to the transport adapter while updating actual callers. |
| `backend/src/app/ScriptingFiles/FullDataScript/run_all.py` | `31f350e3526a` | Reviewed: zero-option argparse command discards Namespace, main owns environment/logging/hook setup and one program report; no pointless empty options object is introduced. Typed incomplete-feed outcome has its documented exit code; uncaught cancellation remains owned by the command hook. Import is side-effect free. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/__init__.py` | `1f506475c98d` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/domain.py` | `d031d85bb39b` | Reviewed: frozen tuple-backed source rows, metric/layout values and typed summaries; layout factories create fresh immutable values, owned by each caller. Stable column/source-field ordering is explicit. Summary serialization creates a fresh compatibility report; final helper-role placement remains a naming/layout disposition. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/errors.py` | `55f0215399a4` | Reviewed/fixed: typed PlayerKindViolation rejects unsupported legacy stat-kind strings without echoing input; existing source/row/coverage/pagination/options errors retain typed context and native validation hierarchy. Raw IDs remain object-typed only at the unvalidated boundary. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/http.py` | `792b4eee84ae` | Reviewed content: minimal runtime transport/client Protocols, frozen borrowed adapters and synchronized caller-owned clients. Context factories close native sessions; GET retries remain native and recovery emits counts only. Native Retry-After has an installed six-hour maximum (not the request socket timeout); no new sleep limit is assumed. Transport options/layout disposition remains explicit. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/moneypuck/__init__.py` | `92d48982cb80` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/moneypuck/domain.py` | `5cae66cc4ccf` | Reviewed: frozen file/URL/quality options with enum-selected inputs; immutable row/report snapshots leave validation before persistence. Paths and defaults are caller-owned values, not import-time resources. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/moneypuck/repository.py` | `eefdd1931c74` | Reviewed: frozen injected transaction factory; one atomic context owns native connection/cursor, parameterized identity/stat writes and operation-local enum-keyed counts/deduplication. Missing historical rows are retained, and returned WriteCounts are frozen. No import I/O or shared mutable indexes. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/moneypuck/services.py` | `6a3c0cac0f22` | Reviewed/fixed: minimal runtime repository Protocol, frozen client/repository/options injection and validation-before-write orchestration. Historical CSV calls the repository file adapter; pure parsing stays in util. Normalization produces frozen tuple/string snapshots; progress fields remain bounded counts/kind, with no source payload logs. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/nhl/__init__.py` | `817f46504c4b` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/nhl/domain.py` | `119e2b09304c` | Reviewed: frozen season/worker/page options, enum-typed jobs and tuple-backed stats/roster snapshots. All fields have one invocation/snapshot lifetime; no mutable shared defaults or resources at import. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/nhl/repository.py` | `dd3aa97acef7` | Reviewed: frozen transaction factories own atomic native connection/cursor contexts; parameterized identity/stat/roster writes retain missing records. Local enum counts, first-profile cache and deterministic final-team selection are not shared state. Native SQL tuple shapes remain an explicit persistence-boundary disposition. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/nhl/services.py` | `197f95d02620` | Reviewed content: minimal runtime repositories, frozen dependencies, joined bounded worker executor and one owned client per job. Pagination checks stable totals, requested size, missing IDs, premature empty/overrun and maximum pages before writes. Frozen domain normalization validates stat equations. Existing option validation remains inline rather than a separate policy; finish its role disposition. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/policy.py` | `4890f14a6a56` | Reviewed/fixed: canonical stat consistency policy now accepts PlayerKind rather than arbitrary strings; legacy string conversion belongs at its caller boundary. Count/duplicate/row policies return typed violations; local deduplication and season coverage precede persistence. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/repository.py` | `e391d1cf1b3d` | Reviewed/fixed: read_csv owns its native file context with the complete original signature/body retained. Shared SQL helpers bind external values; identifier/layout fragments come from canonical layout factories. Native heterogeneous insert tuples remain persistence-edge values, and transaction ownership stays with concrete repository callers. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/schedule/__init__.py` | `a935cb36a63d` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/schedule/domain.py` | `b2439324edef` | Reviewed: frozen season/count options and tuple-backed validated game snapshots with separately owned read counts. No mutable shared state or import-time resources. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/schedule/repository.py` | `2ab1ac0c664a` | Reviewed: frozen transaction factory owns one atomic native connection/cursor; bound retain-missing schedule upserts and local before/after counts become frozen summary values. Source identifiers and scores are bound values, not SQL fragments. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/schedule/services.py` | `127956ea8b9a` | Reviewed content: frozen injected client/repository/options; cursor dates must advance and terminate within the requested season range, data quality validates before persistence. Regular-season game dictionaries are filtered before strict validation and mapped to frozen domain rows. ScheduleDay raw-game snapshot finding must preserve that filter order. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/schemas.py` | `9ff6ad1107ff` | Reviewed/fixed: ScheduleDay reuses immutable JSON-string PageSnapshots and returns detached raw game dictionaries. Input/serialization aliases and native date output remain unchanged, and nonregular rows still filter before strict game validation. Native validator ValueError leaves remain a precise framework/type disposition to resolve. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/__init__.py` | `2e3fb5387200` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/fakes.py` | `75965991228f` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/fixtures.py` | `ece7fceed4ac` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/identities.py` | `8aed5600a218` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/responses.py` | `015d5898a453` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/scenarios.py` | `142c5682179b` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/strategies.py` | `b39f66564425` | Pending semantic review. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/util.py` | `91298dbbc223` | Reviewed/fixed: file opening moved to the source repository adapter; pure CSV parsing/normalization remains here. Finite Decimal conversion, stable row hashing and shared season calendar remain unchanged. The moved internal helper has no compatibility wrapper because its sole actual caller was updated. |
| `backend/src/app/ScriptingFiles/FullDataScript/team_stints.py` | `a39bf2c13fcd` | Reviewed content: fixed SQL reconstructs canonical missing assignments with bound season parameters; caller owns transaction and typed ordered-range failure. Finding: finally cursor.close can replace a primary execute/fetch failure; move both read/write operations under existing complete_cleanup ownership. Error/repository/SQL compatibility role placement remains explicit. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/__init__.py` | `9f4c5a1e1829` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/domain.py` | `f5573df5f967` | Reviewed: frozen invocation/stage/run identity and monotonic start time; fields returns a fresh mapping without mutating its parent invocation. No import-time resources or shared state. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/errors.py` | `dffabfa0c590` | Reviewed: typed job/source errors and batch failure with an independent mapping-proxy copy of committed progress. Cause ownership stays with the raising call site; persisted explanatory text does not enter runtime logs. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/repository.py` | `eb4bd3d6e834` | Reviewed/fixed: durable count projection accepts exact nonnegative integers, matching the existing inferred-count rule; booleans, negatives and other invalid values use the supplied fallback. Bound durable-run SQL and advisory-lock cleanup remain scoped and primary-preserving. Concrete adapter seam remains a final typing disposition. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/services.py` | `8bd918e13f25` | Reviewed: fresh immutable ingestion contexts derived from supplied invocation identity; no logging configuration or resource construction. Progress uses lazy fixed text and explicit fields, with final allowlist/bounds owned by the shared formatter. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/tests/__init__.py` | `512cd1b444a4` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/tests/fakes.py` | `7610a1574dfb` | Reviewed: excluded source-only probes own mutable event/context observations for one fixture. Injected completion/reporting/work failures exercise cleanup and durable-run error ownership; the factory records closure in finally. They are resource probes rather than shared immutable domain values. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/util.py` | `51453fb01dc8` | Reviewed: pure explicit integer count projection, excludes booleans via exact type, and reports committed counts only when write count fields exist. No guessed writes or mutation of the supplied report. |
| `backend/src/app/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `backend/src/app/api/__init__.py` | `ac8dadf50d98` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/api/domain.py` | `dc0d36b232fe` | Reviewed/fixed: frozen PlayerQuery now crosses the route/service/repository boundary; SummarySelection owns immutable bindings and pagination/sort options. Database row snapshots remain frozen, and response mappings are newly owned per call. |
| `backend/src/app/api/errors.py` | `bd34cb531625` | Reviewed: dedicated typed failures retain IDs/seasons and public HTTP envelopes. Common exception inheritance supplies the framework handler contract; exception mutability is native traceback/annotation behavior, not reusable application state. |
| `backend/src/app/api/policy.py` | `8f799d93d8d1` | Reviewed: pure historical cents/season calculation, local immutable threshold data and guarded next selection; no I/O or module mutable state. Fixed published policy values are not logging/environment tunables. |
| `backend/src/app/api/queries.py` | `eb3a586b0e03` | Reviewed: immutable fixed SQL definitions only; named binds, explicit TOTAL/team-stint precedence, stable ordering, season visibility and existing cap/model selection policy. No execution or mutable import state. |
| `backend/src/app/api/repository.py` | `dfea9e09b6bc` | Reviewed/fixed: minimal runtime-checkable read Protocol and frozen borrowed session adapter. SummarySelection replaces threaded options, with immutable bindings copied into local execution parameters. SQL fragments remain code-controlled and request values remain bound. |
| `backend/src/app/api/routes.py` | `9c15c287dd18` | Reviewed/fixed: router built explicitly, named validation aliases and per-request context-owned session; synchronous database routes retain native threadpool execution. PlayerQuery is constructed once from validated request fields; HTTP names/defaults are unchanged. |
| `backend/src/app/api/schemas.py` | `d7fbc367ffcc` | Reviewed content: native per-response Pydantic validation graphs with forbidden extras and explicit published wire enums. Containers are owned validation/serialization buffers, not frozen domain values or shared application state; final boundary disposition is recorded below. |
| `backend/src/app/api/service.py` | `7f645ee7cfc4` | Reviewed/fixed: frozen injected repository/date; players consumes the existing PlayerQuery directly and uses its pagination fields. Season/identity guards and newly owned response aggregates remain unchanged. |
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
| `backend/src/app/shared/observability/domain.py` | `4be6daaf0f62` | Reviewed: frozen settings, invocation/request/failure values, narrow outcomes and fresh context mappings; monotonic durations derive from invocation-owned start time. Explicit numeric severities preserve the native logging protocol. Settings parsing reads supplied mappings only and exposes typed sanitized configuration failures. |
| `backend/src/app/shared/observability/errors.py` | `a88b112c9f87` | Reviewed: one typed exception per settings/ownership/configuration/bounds failure; only exception classes define handwritten constructors, store context and build messages. No import resources or state. |
| `backend/src/app/shared/observability/formatting.py` | `a0e4f7f2af9a` | Reviewed/fixed: DiagnosticCollection now contains only frozen StackFrame/ExceptionSnapshot models with tuple nesting; mutable model_dump copies exist only at serialization. Bounded traversal, cycle detection, primitive allowlists and byte limits remain. Hostile dictionary metadata faults cannot escape rendering; source messages/values remain excluded. |
| `backend/src/app/shared/observability/lifecycle.py` | `7e68a9702da3` | Re-reviewed: frozen ASGI adapter retains native protocol lifetime and primary exception identity. Immutable collected snapshots validate directly into the lifecycle report; hostile exception dictionary faults now produce a bounded truncated safe report. Delivery faults still attach only secondary metadata. |
| `backend/src/app/shared/observability/policy.py` | `aebdde2475d4` | Reviewed/fixed: limit validation returns violations; frozen native record filters normalize severity and suppress reported duplicates. Best-effort exception metadata removal catches BaseException only at that boundary; native host tests retain safe output with hostile metadata. |
| `backend/src/app/shared/observability/requests.py` | `969fca18a440` | Reviewed/fixed: frozen ASGI adapter retains request-local state, streaming order, exact generated IDs and controlled templates. Best-effort exception annotation cannot replace the primary when attribute access raises cancellation/interrupt. Original failures still propagate; native ASGI awaits retain framework lifetime. |
| `backend/src/app/shared/observability/schemas.py` | `c2bd8d7e94cc` | Reviewed: frozen extra-forbidden Pydantic lifecycle graphs with tuple collections, bounded identifiers/frame lines/depth and finite input size. Host protocol payloads validate before severity/event promotion; invalid reports remain generic safe dependency events. |
| `backend/src/app/shared/observability/services.py` | `b2a363ead406` | Reviewed: frozen command hook, fresh invocation fields, main/approved-lifespan-owned native handler and exception-hook configuration, no import-time installation. Idempotent named-handler ownership rejects incompatible settings; dependency noise remains bounded and propagated host errors reuse one safe path. |
| `backend/src/app/shared/observability/sinks.py` | `d88c98db6900` | Reviewed: minimal runtime-checkable stream Protocol, frozen borrowed stream wrapper and one bounded fallback write on ordinary sink failure. No recursive logging/raw-record error report; cancellation/interrupt is not swallowed. Handler construction validates limits and remains owned by configured entrypoints. |
| `backend/src/app/shared/observability/tests/__init__.py` | `0bd51b497d66` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/shared/observability/tests/app_probe.py` | `65720d0ca9e8` | Pending semantic review. |
| `backend/src/app/shared/observability/tests/fakes.py` | `b86dd91a0c02` | Reviewed: source-only factories create independent native records/errors, bounded cause chains and real HTTP/SQLAlchemy payload boundaries. MetadataAccessError intentionally raises an injected fault at native attribute access to reproduce annotation failures; returning a policy violation cannot simulate that contract. Fault doubles are excluded from production artifacts; no import-time resources. |
| `backend/src/app/shared/observability/tests/fixtures.py` | `9acfed4652a5` | Pending semantic review. |
| `backend/src/app/shared/observability/tests/lifecycle.py` | `747a33dcdd67` | Pending semantic review. |
| `backend/src/app/shared/observability/tests/requests.py` | `5f8a1b294d3c` | Pending semantic review. |
| `backend/src/app/shared/observability/tests/verify_http.py` | `9dbb5357811a` | Pending semantic review. |
| `backend/src/app/shared/observability/tests/verify_logs.py` | `c4c01b8e8959` | Pending semantic review. |
| `backend/src/app/shared/observability/util.py` | `72ebc71f109f` | Reviewed/fixed: narrow metadata guards contain BaseException from untrusted attribute access only. Missing/unreadable metadata marks exception snapshots truncated; ordinary application cancellation/interrupt remains owned by the caller. Scope and native route extraction remain request-local. |
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
| `tests/backend/test_api_service.py` | `0f1f13576979` | Pending complete semantic review; updated PlayerQuery scenarios are fixture-owned. |
| `tests/backend/test_capspace.py` | `aaf46338a807` | Pending semantic review. |
| `tests/backend/test_capspace_postgres_integration.py` | `fc816dd7ade8` | Pending semantic review. |
| `tests/backend/test_cli_contracts.py` | `93090bedf255` | Pending semantic review. |
| `tests/backend/test_command_cancellation.py` | `a67078ec6e12` | Pending semantic review. |
| `tests/backend/test_command_logging.py` | `4a1ee6437e7f` | Pending semantic review. |
| `tests/backend/test_config.py` | `7624d1154587` | Pending semantic review. |
| `tests/backend/test_container_smoke.py` | `02fdc5a44940` | Reviewed: native HTTPError/BytesIO fixtures cover handled status, invalid bytes, read/close failures, cancellation, interruption and successful/decode-failed responses; no real network. Readiness and contract specimens are read-only, observations are fixture-owned. |
| `tests/backend/test_contract_domain.py` | `a992295230c4` | Pending semantic review. |
| `tests/backend/test_contract_lifecycle.py` | `b823831689bb` | Pending semantic review. |
| `tests/backend/test_contract_lifecycle_postgres.py` | `820899fbe154` | Pending semantic review. |
| `tests/backend/test_contract_parsing.py` | `3a3ca5de4c15` | Pending semantic review. |
| `tests/backend/test_database_cleanup.py` | `6cd3fbacf88d` | Reviewed: fixture-scoped typed failures/probes and original-cause checks; hostile repr, overridden annotation and invalid native notes cannot mask primary or skip close. Both formats omit secrets and retain bounded secondary diagnostics. |
| `tests/backend/test_database_transactions.py` | `2c682bdcfe33` | Pending semantic review. |
| `tests/backend/test_historical_options.py` | `6b5661805392` | Pending semantic review. |
| `tests/backend/test_ingestion.py` | `dffb4dca8d34` | Pending semantic review. |
| `tests/backend/test_ingestion_logging.py` | `56c6d291e880` | Pending semantic review. |
| `tests/backend/test_lifecycle_logging.py` | `86fa51212d53` | Pending semantic review. |
| `tests/backend/test_logging_policy.py` | `223faf441435` | Pending semantic review. |
| `tests/backend/test_logging_startup.py` | `762d56384b27` | Pending semantic review. |
| `tests/backend/test_migration_tooling.py` | `33e29174d135` | Pending semantic review. |
| `tests/backend/test_openapi_contract.py` | `205f0a706841` | Pending semantic review. |
| `tests/backend/test_operational_errors.py` | `001eb514484d` | Pending semantic review. |
| `tests/backend/test_postgres_integration.py` | `189cc1a86e8d` | Pending complete semantic review; updated PlayerQuery scenarios are fixture-owned. |
| `tests/backend/test_python_rules.py` | `e5fab98155b0` | Pending semantic review. |
| `tests/backend/test_request_logging.py` | `1105df66f125` | Pending semantic review. |
| `tests/backend/test_roster_status_service.py` | `f21e6de8469b` | Pending semantic review. |
| `tests/backend/test_runtime_resources.py` | `2c135b804ce4` | Pending semantic review. |
| `tests/backend/test_source_identity.py` | `fe3873e02c25` | Pending semantic review. |
| `tests/backend/test_source_identity_postgres.py` | `d4c5cd014abc` | Pending semantic review. |
| `tests/backend/test_source_ingestion.py` | `5907bf467439` | Pending semantic review. |
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

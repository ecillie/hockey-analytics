# Python semantic audit checkpoint

File-by-file content inspection is complete; findings remain unresolved. This is
not phase-7 acceptance. Scope is all
245 tracked/new Python files in the acceptance worktree, with source digests
updated after `54b5e18`. Digests identify exactly what was inspected; changed
files require re-review.
Generated artifacts, environments and retired `.py.txt` loaders are not source
entries. The structural gate separately checks all supported executable roots.

Read `~/.codex/python-guidelines.md` before this review. Mechanical lint, format,
type, structural, test and package results do not waive semantic decisions.
18 empty files and 20 module-docstring-only package files have no executable
behavior to assess. 207 other files have received the content review
recorded below; unresolved findings and layout/boundary decisions are explicit.
Inspection does not accept the recorded findings.

Open release decisions include Vercel's exported ASGI application, Alembic's
framework-executed bootstrap, intentional source-only failing test doubles,
remaining source/entrypoint role layout, and frozen historical migration compatibility.
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
  Canonical option/policy/reporting owners, exact contract SQL tuple types,
  the abstract durable-run seam and public schema helper are now resolved below.
  Contract repository/service directories are now resolved below. Remaining
  source helper and compatibility-entrypoint
  judgments stay explicit; these fixes do not waive them.
- ScheduleDay aliasing, durable boolean/negative counts, CSV file-adapter placement
  and broad stat-kind selection are resolved in the source-boundary checkpoint.
  Valid legacy stat-kind strings and regular-season filtering remain compatible.
- Cursor/error-response ownership, roster transport placement, immutable roster
  evidence and typed native validator leaves are resolved in the resource-edge
  checkpoint. Three disposable engine fixtures also guard setup before yield,
  and their transactions reuse production ownership rather than copying it.
- Inspection helpers no longer resolve/scan files during ordinary import, and
  the real HTTP/log verifiers now enforce exact IDs, strict bodies, severity,
  mode thresholds and absence of orphan errors. Actual logged correlation counts
  distinguish the intentionally silent INFO health request.
- The final two inspected-test findings, ingestion scenario arrangement and
  startup host-program resource ownership, are resolved below. Source-only
  native fault doubles still need their precise final disposition with the
  remaining role work and framework/historical decisions; green checks
  do not waive those decisions.

## Canonical contract roles and tracking interface findings resolved

Four frozen option/limit classes now live in domain.py, their three unchanged
checks live in policy.py, and four pure reporting helpers live in util.py.
Runtime callers import those canonical owners; options/reporting compatibility
bindings preserve the exact objects. Native JSON decoding in domain snapshot
properties avoids a reverse utility dependency while retaining fresh copies.
Complete AST comparison proves all 11 moved definitions unchanged, and seven
runtime modules differ only in imports or type annotations/declarations. Every
contract-repository string constant and SQL tuple construction remains identical.

Exact season/source-record insert aliases and a stored-season pair replace broad
contract SQL tuple types; selection values narrow to integers and strings. The
decorator consumes a runtime-checkable IngestionRun exposing only read-only ID,
succeed and fail. Both the PostgreSQL adapter and the in-memory fake satisfy that
interface; the context still owns native resources. Native adapter/factory code
is unchanged. The public render_schema_text helper replaces the unguarded private
name at every actual caller, with identical schema/command behavior. The generated
cancellation driver now constructs its failures inside guarded main and returns
the command's actual exit. Remaining role/framework decisions are separate.

## Contract adapter and service directories resolved

The repository and services role files have grown into directories, preserving
their existing qualified module names for historical callers. Active persistence
and profile HTTP adapters now live under repository; active orchestration lives
under services. The three old descriptive modules contain explicit compatibility
exports. Runtime callers and native retry/parser instrumentation use canonical
owners, so wrap-through checks still observe actual execution.

Against `776d69a`, all five moved modules and six callers have identical
executable AST after imports are removed. SQL, signatures, defaults, tuple values,
worker coordination, parser calls and resource cleanup remain unchanged. All 33
compatibility exports have exact canonical identity; all 225 compared focused
test IDs are unchanged. New source files have content-review entries, bringing
the ledger to 240 files. The unchanged native import-discovery test gains one
net fresh-process case because role package initializers replace two ordinary
modules while three canonical child modules are added.

The first full run caught unstaged removed files in the Git source-scope test.
The only missing paths were the old repository.py/services.py; staging the
completed moves made the unchanged scope test pass. Full verification is rerun
against the staged tree. This does not waive active write-context, remaining
source/entrypoint roles, framework/historical/fault-double or hosted decisions.

## Shared source transport setup and NHL option policy resolved

Source persistence is now a repository role directory, preserving its qualified
module and complete AST. The transport is repository/http.py; frozen transport
options live in domain.py with unchanged defaults. Actual callers use canonical
owners and the legacy http module binds the ten previously defined objects to
their exact canonical identities. Native Retry, mount and header statements are
unchanged; no new retry/sleep limits or library-default overrides are introduced.

Session construction is now guarded through configuration: any setup failure
closes the constructed native session once, keeps the original error/cancellation/
interrupt and cause, and retains cleanup failure only as secondary. Eighteen
native fault cases fail before this fix and pass afterward. Fixture fallback
ownership and patch restoration also protect test setup/teardown. The canonical
NHL options policy returns the original violation; its call site raises before
workers/clients. The condition and message are unchanged, and four named invalid
boundaries prove no clients or persistence. Existing test bodies and six source
consumer bodies remain unchanged apart from imports.

This setup guard does not establish body-teardown failure preservation. A separate
native-session probe injects a close failure during source-client, historical-
profile and active-profile teardown. All nine error/cancellation/interruption
paths replace their original failure with the close failure. That concrete shared
session-lifetime finding was unresolved at that checkpoint; the following section
records its fix.

## Native HTTP session lifetime finding resolved

One Session-specific owner guard registers native exit with ExitStack before
native entry, then runs cleanup through complete_cleanup. The source-client,
historical-profile and active-profile owners use it; borrowed factories remain
caller-owned. Native Session enter/exit are retained, including cleanup when an
allocated session fails to enter. An existing primary error/cancellation/interrupt
and cause are preserved; cleanup becomes secondary, or propagates itself when it
is the sole failure. The wrapper relies on native Session exit closing without
suppression or exception-dependent behavior, verified against the installed code.

The 96 named native entry/body/cleanup combinations reproduce 63 failures against
the exact preceding owner definitions and pass after the fix. All 18 setup cases
still pass; the original nine teardown probes now preserve each primary. A shared
fixture-only close observer still forwards to the original native close and has
an unchanged method body. Native resources and patches remain context-owned.
All prior 68 source-test IDs are retained. Exact AST comparison permits only the
shared lifetime guard/import and three owner handoffs in the two transport modules;
request, retry, parser, configuration and borrowed-factory code is unchanged.

## Active write values and team-stint repository findings resolved

Canonical active SQL writers now accept frozen contract/season write values.
Resolved scalar signing/owning team IDs cross that boundary; the mutable team
lookup stays in snapshot preparation, and the name index remains local to its
save operation. The two existing keyword writer boundaries construct those values
for compatibility. The cap-percentage invariant returns its existing typed error
from policy; the writer raises at the same point after the database cap read.
Comparisons against `54b5e18` cover 216 contract and 24 season cases, retaining
outcomes, exact SQL and bound values across null/zero caps, existing rows,
nullable team resolution, contract types and cap violations.

Team-stint SQL, range policy and typed error now have their own concept role
files, with the original package import retained through exact bindings. All SQL
constant AST and the moved error class AST are unchanged. Ten valid-range
comparisons retain counts, bindings and one cursor close. Both reversed-range
regressions fail before the fix and now raise the typed error before acquiring a
cursor. Repair accepts a minimal runtime-checkable query Protocol; two falsy
injected-query cases preserve bounds/result and commit-or-rollback/close ownership.
Existing CLI defaults, help/parser/main and report semantics remain unchanged.
Remaining source helper/entrypoint, framework/historical/fault-double and hosted
decisions are separate from these resolved findings.

## Ingestion scenarios and startup ownership findings resolved

Ingestion expected summaries are immutable pairs; each stage receives a fresh
native dictionary. Roster-command failures are constructed in fixtures rather
than shared across parametrized calls. Invalid native rows and ambiguous-player
SQL setup now belong to fixtures, including the original precondition checks.
Retained-stage observations and MoneyPuck results use frozen named bindings.
Their event buffer and borrowed engine retain their native fixture owners;
MoneyPuck summaries remain immutable domain values. All 60 collected test IDs
and the existing native boundary, SQL, rollback and retention assertions remain.

Generated startup probes have explicit main/module guards and shared exit codes.
ExitStack/closing own host capture streams and handlers, unregister host/root
attachments and close on failed setup or assertions. Engine factories enter the
existing primary-preserving SQLite guard before constructing sessions. A bounded
fresh-process fault probe injects session construction failure and cancellation:
the preceding programs dispose zero engines on that path; the current programs
dispose once and preserve each original failure. The repeated lifespan timeout,
real Vercel entry import and approved hook remain unchanged. The generated host
is deliberately a process entry point; it does not authorize import-time logging
configuration in application libraries.

## HTTP and host observation findings resolved

Named native HTTP, streaming, propagated-host and concurrent observations replace
positional bundles. Actual captured records travel with observations across
pytest phases. This corrects a vacuous earlier lifespan no-stopped check: an
injected false stopped event passed all eight preceding cases and now fails all
eight. A ready-count control checks the successful-startup side. Native host
records and logging setup are fixture-owned; generated command/Alembic drivers
use explicit main, guarded module entry and native stream/handler ownership.
Other explicit test/host-program and runtime/framework findings remain open.

## Command/source scenario findings resolved

CLI argument/summary/error templates are immutable descriptions and fresh fixture
values; observation streams have native context ownership. Named command, repair,
pagination, session, validator and quality cases replace positional dependency
bundles. Native retry sessions and external-output options belong to fixtures.
The contract-conflict fixture captures preview nonmutation before SQL setup,
retaining both behaviors in the original test. Other explicit test/host-program
and runtime/framework findings remain open.

## Native test-resource and logging setup findings resolved

Source-only SQLite/request contexts now establish cleanup before setup and use
the existing primary-preserving cleanup helper. Native dependency health faults
close the generator and engine even when close also fails. Lifespan fixtures
use the engine guard around setup and listener removal; frozen observations keep
host-record/logging setup outside bodies. Generated logging inputs preserve the
original Unicode/format spaces, and native HTTP response streams are fixture-owned.
Other explicit test/host-program and runtime/framework findings remain open.

## Fixture-input findings resolved

Contract, roster, API and ML parameter examples now use immutable descriptions
and fresh fixture-owned native dictionaries, errors and arrays. Generated
formatted contract inputs, effective options, parser instrumentation and ML
feature/artifact inputs are arranged outside test bodies. Named frozen scenarios
carry retry, reconciliation, API service and ML expected-failure collaborators;
mutable observation/native boundary buffers remain local to their fixtures.
Other recorded test/resource and framework/role findings remain open.

## Adapter cursor and contract-fixture ownership resolved

Eleven runtime cursor scopes now use the existing shared primary-preserving
guard. Native query/cancellation identity survives close failure, transaction
ownership stays at the existing factory and roster connections remain borrowed.
Complete AST comparison permits only guarded acquisition/import changes in six
adapters. Contract scenario setup is context-owned before seeding; rollback,
trigger removal and close are all attempted without masking a primary failure.
Explicit disposable settings and guarded cursors also protect source identity,
backfill and advisory-lock fixtures. Other recorded fixture findings remain open.

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
All 245 files have content-inspection dispositions; unresolved findings still
require fixes or precise decisions. Passing gates does not accept them implicitly.

## File ledger

| Source | SHA-256 prefix | Review disposition |
| --- | --- | --- |
| `backend/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `backend/database/backfill_team_stints.py` | `0833870d311d` | Re-reviewed/fixed: repair accepts the minimal runtime-checkable TeamStintQuery, selecting the established plan/apply callable only for None. Falsy injected queries are retained. Existing defaults, CLI main/parser, report flags, commit/dry-run rollback and primary-preserving rollback/close remain; two injected-query cases verify range, result and transaction ownership. |
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
| `backend/export_openapi.py` | `4832c775dc48` | Re-reviewed/fixed: render_schema_text is a public descriptive helper and all actual callers/injected command seams use it. Schema-only construction, deterministic JSON, frozen options, main-owned diagnostics and check/write paths are unchanged; full AST comparison permits only the helper rename. |
| `backend/index.py` | `6a1e64c5ed23` | Reviewed content: required ASGI export calls runtime factory at module load; mutable application and dotenv/factory import work need exact owner disposition. |
| `backend/migrations/env.py` | `68e8ae9c844a` | Reviewed content: thin Alembic-executed main adapter; success returns to framework, failures exit. Load-time bootstrap disposition remains open. |
| `backend/migrations/versions/20260910_0001_initial_schema.py` | `7e09b5e51a37` | Reviewed content: frozen checksum/schema and revision metadata; external reads/SQL only during revision execution. Historical generic guard error, else branch and cleanup contract require frozen-migration disposition; do not rewrite history silently. |
| `backend/migrations/versions/20260920_0002_capspace_source.py` | `935a3ecabd9c` | Reviewed: immutable revision metadata and fixed SQL only in upgrade/downgrade; history preservation included in frozen-migration disposition. |
| `backend/src/app/ScriptingFiles/FullDataScript/capspace.py` | `59f079d89351` | Re-reviewed: transport imports target canonical repository.http; historical service/repository qualified names remain unchanged as role packages. Complete executable AST is identical. Public command/parser, options, resource factories, compatibility exports and program/diagnostic contracts remain; remaining compatibility-entrypoint role judgments are explicit. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/__init__.py` | `78dc82a8112a` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/active_repository.py` | `0068b88a19d9` | Re-reviewed/fixed: the two published keyword writer boundaries preserve their prior call shapes and assemble immutable write values before delegating. Remaining repository/factory exports retain canonical identity. Legacy comparisons cover 216 contract and 24 season cases with identical outcomes, exact SQL and bound values, including null/zero caps, existing rows, nullable teams, entry-level types and cap violations. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/active_services.py` | `6892196dc012` | Re-reviewed/fixed: explicit compatibility exports point to the exact canonical services.active orchestration/future resolver. Actual runtime callers use the canonical owner; no duplicate service implementation or import resource work remains. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/domain.py` | `6871f82c431b` | Re-reviewed/fixed: ActiveContractWrite and ActiveSeasonWrite are frozen scalar/domain-value records. Team IDs are resolved before handoff; no mutable team lookup is retained in write values. Existing contract/profile/options defaults and detached JSON snapshots remain unchanged. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/errors.py` | `427b82d3ef9b` | Reviewed/fixed: typed ContractOptionError now has its canonical errors role while options retains its public compatibility export. Marker exception hierarchy groups typed parsing/reconciliation leaves; persisted source details are never copied into runtime logs. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/http.py` | `56e198cbc309` | Re-reviewed/fixed: explicit compatibility exports retain all 23 defined transport functions, Protocols, adapters and factory aliases with exact canonical repository.http identity. Runtime and native parser/retry instrumentation import the canonical implementation. No duplicated transport behavior or import resource acquisition remains. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/options.py` | `fc0381f0be50` | Re-reviewed/fixed: compatibility bindings refer to the exact canonical domain values, policy checks and typed error. Actual runtime callers import canonical owners; existing test/public import paths retain identity and behavior. No validation implementation, resources or import-time I/O remains here. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/policy.py` | `60e66722bf58` | Re-reviewed/fixed: ActiveSeasonCapPolicy owns the existing nullable greater-than-one percentage invariant and returns the same typed contextual error. The SQL writer raises at the same point after reading the cap. Existing option/worker/identity/reconciliation policies remain unchanged. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/reporting.py` | `07e9be700146` | Re-reviewed/fixed: explicit compatibility bindings refer to the canonical pure utility helpers and SourceProfileRecords alias. Actual runtime callers import util directly; compatibility identity is checked. No duplicate implementation, resources or import-time I/O remains here. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/repository/__init__.py` | `4822efeff4ad` | Re-reviewed/fixed: the canonical repository role is now a directory; the historical adapter retains the identical qualified module, complete executable AST, SQL constants, typed batch tuples, immutable contexts, reconciliation and primary-preserving factories. Active and transport adapters have sibling owners. Native borrowed cursor/write-context data remains local to persistence. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/repository/active.py` | `f47e8d7ac18e` | Re-reviewed/fixed: canonical SQL writers consume immutable contract/season write values and the named exact count pair. Team lookup stays local to snapshot preparation, and the mutable name index stays inside its save operation. Legacy transcript comparisons preserve all SQL/bindings/outcomes; real integration proves idempotence/upserts/rollback. Borrowed cursor and guarded transaction factories are unchanged. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/repository/http.py` | `9d15e51aee29` | Re-reviewed/fixed: both owned profile factories use the shared Session-specific lifetime guard. Entry and body failure/cancellation/interruption retain original identity/cause while cleanup is attempted once and retained only as secondary; sole cleanup failures propagate. Exact AST comparison preserves every other request/retry/parser/configuration and borrowed-factory statement. Native session protocols and identity fallback remain unchanged. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/schemas/__init__.py` | `8c25f29beb35` | Reviewed: explicit public document imports and established tag helper aliases; dependencies now inspected. No I/O or mutable application state at import. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/schemas/active.py` | `da783f50d133` | Reviewed: source-boundary parsing validates index/profile shape and slug, minimum row coverage, native date conversion and contiguous seasons. Empty/duplicate seasons fail in parse_mapping_contract before min/index operations. Parsed contracts leave the boundary as frozen values. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/schemas/contracts.py` | `9c133d82d1a6` | Reviewed: boundary-only JSON/table parsing, explicit null/empty distinction, finite payload traversal and typed parse failures. Source identity and nonempty/unique season guards precede normalization; immutable domain snapshots isolate native parser mappings. No I/O/logging. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/schemas/documents.py` | `b8e438d701ac` | Reviewed content: Pydantic validates external JSON and native BeautifulSoup owns the parse tree. SourceDocument is a newly owned boundary buffer, not shared/frozen domain state; fresh page decoding and explicit text/attribute narrowing. Boundary mutability disposition applies. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/schemas/serialization.py` | `d48fc2cec40c` | Reviewed: asdict creates independent persistence snapshots, internal JSON-string fields are removed, decoded public payloads and season serialization preserve the stored compatibility shape. No I/O or leaked mutable domain state. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/services/__init__.py` | `3c0707075093` | Re-reviewed/fixed: the service role is now a directory; historical orchestration retains its identical qualified module and executable AST, importing canonical repository.http. Injected limits, joined owned workers, independent batch commits, stored summary/cause and safe progress semantics remain unchanged. Active orchestration has a sibling canonical service. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/services/active.py` | `91368c3a87f0` | Re-reviewed: request-recovery import targets the canonical source transport; complete executable AST is unchanged. Frozen injected active orchestration, bounded requests, joined workers and validation-before-write behavior remain. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/__init__.py` | `0e8f75076203` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/fakes.py` | `6fe16a794b45` | Re-reviewed: fixture-owned session/run/repository observations and bounded barriers retain native failure/ownership behavior. ReconciliationScenario now names immutable matches and exact failure reason. No import resources, shared mutable defaults or runtime artifact exports. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/fixtures.py` | `438c7bf17938` | Reviewed/fixed: saved response values are freshly arranged and file reads occur only when called. Disposable engine setup/yield/teardown now lives inside the production resource guard, including pre-yield skips/failures; numeric source count checks are explicit. No import-time database or upstream access. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/postgres.py` | `5418e7dbc637` | Re-reviewed: ContractCounts names the repeated exact count tuple. ContractConflictScenario retains a read-only typed preview result and immutable before/after counts, allowing SQL setup in fixtures without losing preview nonmutation assertions. Existing guarded connection/cursor ownership and committed-batch/session semantics are unchanged. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/strategies.py` | `33ef74d9b01c` | Reviewed/fixed: Hypothesis builds frozen CurrencyExample/SeasonExample values over the original finite Decimal and inclusive year spaces. Instance-derived formatted inputs and expected cents/year are arranged outside test bodies. No shared mutable examples, resource work or import I/O. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/tests/transport.py` | `3d7ade0e7332` | Re-reviewed/fixed: retry scenario names native session/sleep collaborators and immutable expected status/error/delays. ParserCalls holds fixture-owned native wrap-through instrumentation, preserving actual parse behavior/counts without replacing a repository. Mutable observations and generated source HTML remain local fixture resources, not claimed immutable production values. |
| `backend/src/app/ScriptingFiles/FullDataScript/contracts/util.py` | `8fa8b5eb4c35` | Re-reviewed/fixed: four unchanged pure profile snapshot/grouping/metrics/count helpers now share the canonical utility role with money/season/text/date conversion. Source grouping and Counter values are local serialization/report outputs, distinct from immutable domain values. Original source snapshots remain freshly decoded; imports perform no environment, resource or database work. |
| `backend/src/app/ScriptingFiles/FullDataScript/ingestion.py` | `8a8ede222845` | Re-reviewed: source client/session imports target the canonical repository.http implementation. Complete executable AST is unchanged, including actual native factory alias, owned/borrowed transport selection, guarded cached summaries and parent terminal diagnostics. Compatibility-entrypoint role judgment remains explicit. |
| `backend/src/app/ScriptingFiles/FullDataScript/ingestion_tracking.py` | `84afd241f897` | Re-reviewed/fixed: failure reporting depends on the minimal runtime-checkable IngestionRun Protocol, exposing only read-only run_id, succeed and fail. The decorator has no concrete PostgreSQL dependency. Complete executable AST is unchanged after imports/types; native callable signatures/metadata, immutable context, stored counts, original failures and best-effort secondary reporting remain. |
| `backend/src/app/ScriptingFiles/FullDataScript/populate_roster_status.py` | `5c7d1f03acbf` | Reviewed: legacy native command boundary builds injected feed/repository services only during invocation, uses explicit None checks, and rolls back incomplete feeds before returning. Main owns logging/hook/exit codes and one report; no Namespace escapes its zero-option parser. Established wire names and asdict summary shape are retained. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/__init__.py` | `e0395eee5ae5` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/ahl_roster_service.py` | `6d2573cc2fd2` | Re-reviewed: actual fetch_validated imports now use the transport adapter. Frozen client/options, explicit season selection, per-team error collection and conflicting-identity rejection preserve their prior behavior and immutable results. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/domain.py` | `b039c9a0e6e7` | Reviewed/fixed: RosterEvidence groups immutable per-sync membership frozensets and completeness facts; it retains no mutable match dictionary. Existing frozen IDs/results/options and enum-derived uppercase database status values remain unchanged. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/errors.py` | `fcad4786f075` | Reviewed: typed JSON, feed and incomplete-sync failures build messages and retain structured context. Source reasons belong to reports/persistence and are not copied by the runtime formatter. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/http_json_client.py` | `365f5501dc10` | Reviewed/fixed: HTTPError response ownership is explicit, close is attempted once and its faults remain secondary to the original HTTP error. Moved fetch_validated preserves its complete signature/body and cause translation. Successful native response contexts, bounded socket timeout and safe JSON/JSONP parsing remain unchanged. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/nhl_roster_service.py` | `d8d48b78b144` | Re-reviewed: actual fetch_validated imports now use the transport adapter. Validated sorted team traversal, immutable roster/error results and incomplete-feed behavior remain unchanged, without import I/O or logger ownership. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/policy.py` | `3fe4da0486ab` | Reviewed/fixed: classification consumes one immutable evidence value rather than six threaded arguments. LTIR, active, minors and unknown precedence and conservative incomplete-feed behavior are unchanged; no I/O or shared state. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/repository.py` | `86a92eb667d0` | Reviewed: minimal runtime repository Protocol and frozen borrowed connection adapter. Native cursor contexts close each fixed/bound query/write, immutable rows/status sets leave persistence, and outer transaction ownership remains with the sync entrypoint. Empty batches do no I/O and source IDs are preserved conservatively. Re-reviewed/fixed: all four borrowed-connection cursor scopes use the shared primary-preserving guard. Connections remain caller-owned and full AST comparison preserves all other behavior/SQL. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/schemas.py` | `3e4461105b5f` | Reviewed: frozen native Pydantic scalar/tuple boundary graphs and strict named feed-ID aliases. Defaults are immutable or native factories; permissive source fields stay at the external shape boundary. No resources or mutable application state at import. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/services.py` | `bfaa47dd6cbf` | Reviewed/fixed: frozen injected feeds/repository/context build RosterEvidence once per sync, copying only match membership into a frozenset. Safe progress counts, identity writes and status decisions retain their prior order; the caller still rolls back incomplete feeds. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/tests/__init__.py` | `ec5000bdb273` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/tests/fakes.py` | `7b5dea773a5e` | Reviewed: in-memory repository/feed/client satisfy actual behavioral seams and deliberately expose falsy empty states. Update/call/mapping buffers belong to one fixture, and native BytesIO response ownership is explicit. No import resource acquisition or shared mutable defaults. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/tests/fixtures.py` | `b9523d20a965` | Reviewed: named fixtures build fresh immutable player identities and independent native feed payload buffers. Data lives in fixture arrangement; no upstream requests, import I/O or shared mutable decorator payloads. |
| `backend/src/app/ScriptingFiles/FullDataScript/roster_status/util.py` | `2bd2b5dd6205` | Reviewed/fixed: transport fetching moved unchanged to the HTTP adapter; this role now contains only pure schema-to-domain parsing, normalization and conservative identity matching. Duplicate/conflicting IDs and ambiguous names/birth dates still fail closed. |
| `backend/src/app/ScriptingFiles/FullDataScript/run_all.py` | `31f350e3526a` | Reviewed: zero-option argparse command discards Namespace, main owns environment/logging/hook setup and one program report; no pointless empty options object is introduced. Typed incomplete-feed outcome has its documented exit code; uncaught cancellation remains owned by the command hook. Import is side-effect free. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/__init__.py` | `1f506475c98d` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/domain.py` | `8b7233618612` | Re-reviewed/fixed: unchanged frozen SourceHttpOptions now has its canonical domain owner; all original defaults/native retry settings remain. Existing tuple-backed rows, layouts and typed summaries retain their behavior. Fresh compatibility summary serialization remains an explicit helper-role disposition. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/errors.py` | `2b5354017443` | Reviewed/fixed: IntegerValueViolation and TeamAbbreviationViolation are typed ValueError-compatible leaves retaining input context without echoing it in their fixed messages. Existing source/row/kind/coverage errors preserve their native hierarchy and typed context. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/http.py` | `6bea216923a9` | Re-reviewed/fixed: explicit compatibility bindings retain the domain options class and canonical repository.http transport functions, Protocols and factories. All ten previously defined objects have exact canonical identity. No duplicated transport implementation or import resource acquisition remains. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/moneypuck/__init__.py` | `92d48982cb80` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/moneypuck/domain.py` | `5cae66cc4ccf` | Reviewed: frozen file/URL/quality options with enum-selected inputs; immutable row/report snapshots leave validation before persistence. Paths and defaults are caller-owned values, not import-time resources. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/moneypuck/repository.py` | `e72697c6ff7d` | Reviewed: frozen injected transaction factory; one atomic context owns native connection/cursor, parameterized identity/stat writes and operation-local enum-keyed counts/deduplication. Missing historical rows are retained, and returned WriteCounts are frozen. No import I/O or shared mutable indexes. Re-reviewed/fixed: the cursor is guarded inside the existing transaction factory; primary query/cancellation identity survives close failure. Complete AST comparison preserves every other statement/signature/SQL value. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/moneypuck/services.py` | `cf19e1a75722` | Re-reviewed: client Protocol imports canonical repository.http. Complete executable AST is unchanged: frozen dependencies, schema/quality checks before persistence and snapshot/hash/count behavior remain. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/nhl/__init__.py` | `817f46504c4b` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/nhl/domain.py` | `119e2b09304c` | Reviewed: frozen season/worker/page options, enum-typed jobs and tuple-backed stats/roster snapshots. All fields have one invocation/snapshot lifetime; no mutable shared defaults or resources at import. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/nhl/policy.py` | `ac3016ebbb4b` | Reviewed/fixed: frozen NhlStatsOptionsPolicy owns the unchanged ordered-range/positive-worker/page-size/page-budget invariant and returns the original typed OptionsViolation or None. It performs no I/O. Actual service boundary tests prove invalid options create no client or persisted snapshot. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/nhl/repository.py` | `8a55343c6fc7` | Reviewed: frozen transaction factories own atomic native connection/cursor contexts; parameterized identity/stat/roster writes retain missing records. Local enum counts, first-profile cache and deterministic final-team selection are not shared state. Native SQL tuple shapes remain an explicit persistence-boundary disposition. Re-reviewed/fixed: stats and roster cursor scopes are guarded inside their existing transaction factories. Complete AST comparison preserves all SQL, signatures and other behavior; cancellation/query failures survive close failure. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/nhl/services.py` | `f4d8caa0009b` | Re-reviewed/fixed: the service raises the value returned by the canonical NHL options policy before worker/client acquisition; client imports canonical repository.http. AST comparison preserves the original condition/error constructor and all other executable statements, worker/row validation, pagination and persistence behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/policy.py` | `4890f14a6a56` | Reviewed/fixed: canonical stat consistency policy now accepts PlayerKind rather than arbitrary strings; legacy string conversion belongs at its caller boundary. Count/duplicate/row policies return typed violations; local deduplication and season coverage precede persistence. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/repository/__init__.py` | `e391d1cf1b3d` | Re-reviewed/fixed: the shared persistence/file role is now a directory, preserving the exact qualified module and complete AST. Bound SQL, file ownership, native batch tuples and concrete caller transaction ownership are unchanged. The transport adapter has a canonical sibling owner; native SQL tuple boundary judgment remains explicit. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/repository/http.py` | `8f66a73d7e49` | Re-reviewed/fixed: open_owned_http_session registers native Session exit with ExitStack before native entry, then complete_cleanup preserves a primary while invoking exit once. All three owned source/profile factories use it. The setup factory guard remains unchanged; native request/retry/recovery/configuration and borrowed adapter bodies are identical. This Session-specific wrapper preserves known native no-suppression semantics and makes no generic context-manager claim. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/schedule/__init__.py` | `a935cb36a63d` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/schedule/domain.py` | `b2439324edef` | Reviewed: frozen season/count options and tuple-backed validated game snapshots with separately owned read counts. No mutable shared state or import-time resources. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/schedule/repository.py` | `466edf6cf264` | Reviewed: frozen transaction factory owns one atomic native connection/cursor; bound retain-missing schedule upserts and local before/after counts become frozen summary values. Source identifiers and scores are bound values, not SQL fragments. Re-reviewed/fixed: cursor ownership uses the shared primary-preserving guard inside the existing transaction. Complete AST comparison preserves all other behavior and SQL. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/schedule/services.py` | `1317f5646358` | Re-reviewed: client Protocol imports canonical repository.http. Complete executable AST is unchanged: regular-game filtering, immutable snapshots, calendar boundaries, minimum-count validation and retained-game persistence remain. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/schemas.py` | `5575f832f2b9` | Reviewed/fixed: native validator failures now raise dedicated typed ValueError subclasses with unchanged messages, and Pydantic retains the typed context. Frozen tuple/string snapshots and source aliases remain intact; nonregular schedule filtering still precedes strict game validation. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/__init__.py` | `2e3fb5387200` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/fakes.py` | `dfb4e5ac60e3` | Re-reviewed: native transport Protocol/options imports target canonical repository.http with exact domain option identity. Complete executable AST is unchanged. In-memory persistence and native owned/borrowed client/session observations remain per fixture. ManagedSession models normal context entry/exit and does not prove native failing-close semantics. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/fixtures.py` | `b99b82190b26` | Reviewed/fixed: all CSV/payload arrangement is fixture-owned. Disposable engine setup/yield/teardown uses the production resource guard, including pre-yield setup faults; test transactions delegate to the production guard with explicit disposable settings/context instead of copying weaker cleanup. File writes/environment patches remain scoped fixtures. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/identities.py` | `8aed5600a218` | Reviewed: pure Hypothesis scenario factory generates equivalent numeric ID representations, independent raw input dictionaries, original hashes and frozen typed jobs/layouts. Mutable rows are deliberately fixture-owned validation inputs; immutable metadata and expected hashes are separate. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/responses.py` | `015d5898a453` | Reviewed: source-only response/session templates build fresh native JSON/CSV graphs on request. Frozen primitive configuration has no shared mutable buffers; lifecycle observations are per fixture. Native throw points and nullcontext factories simulate actual transport/borrowed-client boundaries, without network or import I/O. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/scenarios.py` | `983aa1f28622` | Re-reviewed/fixed: SessionCloseProbe owns fixture-native session/callback/secondary-failure and close observations; its forwarding method is identical to the prior setup observer. Frozen setup/lifetime bindings separate fresh primary/cause and owner/entry-mode fields from the native resource. The lifetime act enters the actual owner and optionally raises its prepared body failure; expected-failure selection distinguishes primary from sole cleanup. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/tests/strategies.py` | `b39f66564425` | Reviewed: pure named optional-number Hypothesis strategy deliberately includes nonfinite/missing numeric boundaries; no shared mutable examples or resource state. |
| `backend/src/app/ScriptingFiles/FullDataScript/source_ingestion/util.py` | `91298dbbc223` | Reviewed/fixed: file opening moved to the source repository adapter; pure CSV parsing/normalization remains here. Finite Decimal conversion, stable row hashing and shared season calendar remain unchanged. The moved internal helper has no compatibility wrapper because its sole actual caller was updated. |
| `backend/src/app/ScriptingFiles/FullDataScript/team_stints/__init__.py` | `98389c81d214` | Reviewed/fixed: exact compatibility bindings retain the original team-stints import path for parameter building, plan/apply queries and typed range error. SQL, policy and errors have canonical owners; import performs no external I/O or resource construction. |
| `backend/src/app/ScriptingFiles/FullDataScript/team_stints/errors.py` | `1bd52deaf535` | Reviewed/fixed: SeasonRangeError moved unchanged, with exact exception class AST, keyword fields and message. The compatibility package exports the same canonical object. |
| `backend/src/app/ScriptingFiles/FullDataScript/team_stints/policy.py` | `ecaafe28b861` | Reviewed/fixed: frozen SeasonRangePolicy returns the existing typed failure only when both optional bounds are present and reversed. The caller raises before resource acquisition. Unbounded, one-sided, equal and ordered ranges preserve native behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/team_stints/repository.py` | `1e544c074b07` | Re-reviewed/fixed: canonical borrowed-connection SQL adapter retains all original SQL constant AST and published query signatures/results. Validation precedes cursor acquisition; both reversed-range cases prove zero cursor operations. The runtime-checkable TeamStintQuery gives repair its minimal injectable persistence interface. Ten legacy valid-range transcript comparisons retain SQL, bindings, counts and one close; native cursor/transaction cleanup remains guarded. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/__init__.py` | `9f4c5a1e1829` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/domain.py` | `f5573df5f967` | Reviewed: frozen invocation/stage/run identity and monotonic start time; fields returns a fresh mapping without mutating its parent invocation. No import-time resources or shared state. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/errors.py` | `dffabfa0c590` | Reviewed: typed job/source errors and batch failure with an independent mapping-proxy copy of committed progress. Cause ownership stays with the raising call site; persisted explanatory text does not enter runtime logs. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/repository.py` | `a9eff0d5b939` | Re-reviewed/fixed: IngestionRun is the minimal runtime-checkable consumer interface; the owned context exposes it while the frozen PostgreSQL adapter keeps native handles internally. Adapter class AST and factory executable AST are unchanged. Exact nonnegative durable counts, bound run SQL, locks and primary-preserving cleanup remain. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/services.py` | `8bd918e13f25` | Reviewed: fresh immutable ingestion contexts derived from supplied invocation identity; no logging configuration or resource construction. Progress uses lazy fixed text and explicit fields, with final allowlist/bounds owned by the shared formatter. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/tests/__init__.py` | `512cd1b444a4` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/ScriptingFiles/FullDataScript/tracking/tests/fakes.py` | `c00a8eb130a3` | Re-reviewed: the in-memory RecordingRun is checked structurally by its Generator[IngestionRun] factory annotation. Native event/context buffers remain local per fixture. Completion/reporting/work fault injection and closure behavior are unchanged; no concrete database implementation is required by the fake. |
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
| `backend/src/app/api/tests/fakes.py` | `a4599da2ce58` | Re-reviewed: immutable input rows and per-fixture observations preserve the consumer-complete read seam; independent PostgreSQL checks own SQL ordering/binding evidence. ServiceScenario now names service/mode collaborators with a constrained mode alias. Native TestClient/resource buffers remain fixture-owned and excluded from artifacts. |
| `backend/src/app/api/tests/fixtures.py` | `eae9d71ecbdb` | Reviewed/fixed: typed immutable API scenarios and deterministic fixed SQL arrange behavior outside test bodies. Disposable engine seeding/yield/teardown now uses the primary-preserving production resource guard; service sessions keep native scoped ownership. Fixed seed SQL is source metadata, not a tunable or import-time query. |
| `backend/src/app/api/util.py` | `f9144c0881f3` | Reviewed: pure conversion into fresh response maps, explicit nullable fields, owned ranking list and stable ID tiebreak; no mutation of frozen repository rows or external effects. |
| `backend/src/app/config.py` | `2e25f8385208` | Reviewed: frozen settings/snapshot, explicit call-time dotenv merge with exports winning, narrow environment selection, typed validation, no import-time external resources. |
| `backend/src/app/database.py` | `24ff1442d13a` | Re-reviewed/fixed: open_database_cursor owns only its borrowed connection cursor and uses complete_cleanup to retain query/cancellation identity while attempting close once. Existing engine/transaction guards retain rollback/disposal/connection ownership and sanitized outcome events; no import-time resource construction. |
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
| `backend/src/app/shared/observability/tests/app_probe.py` | `65720d0ca9e8` | Reviewed: excluded read-only probe factory adds deterministic native numeric and streaming failures to the production app only when called. Stream yields its first chunk before native conversion failure; endpoint metadata stays outside OpenAPI. No module-level app or import-time resource startup. |
| `backend/src/app/shared/observability/tests/fakes.py` | `db0318c07923` | Re-reviewed/fixed: Hypothesis generates complete fresh FormattingScenario records/formatters over the original nonempty Unicode secret space and both formats. Native error/cause/notes remain unraised record inputs and no formatter is configured at import. Existing independent hostile metadata/fault and capture probes remain excluded from artifacts with per-fixture state. |
| `backend/src/app/shared/observability/tests/fixtures.py` | `9acfed4652a5` | Reviewed: native logger/excepthook settings are isolated with pytest monkeypatch and per-fixture handler ownership; only a newly installed diagnostic handler is closed. No logging configuration or database/resource acquisition occurs at module import. |
| `backend/src/app/shared/observability/tests/lifecycle.py` | `f79c39a28fbf` | Re-reviewed/fixed: LifecycleObservation now retains its actual captured records as well as the native failure/host record. This prevents call-phase resets from making no-false-stopped assertions vacuous. Frozen scenario/resource bindings and bounded native ASGI exercise remain unchanged; native log objects are fixture-owned handles. |
| `backend/src/app/shared/observability/tests/requests.py` | `0a29e894792c` | Re-reviewed/fixed: frozen HTTP, streaming, propagated-host and concurrent request observations replace positional collaborator bundles. CapturedRecords preserves each actual log set across pytest phases; scope/transport aliases preserve native ASGI shapes. HostFilters contains distinct reported-filter instances so cross-instance duplicate consumption remains tested. Shared input state is deliberately aliased fixture data; native TaskGroup and timeout behavior are unchanged. |
| `backend/src/app/shared/observability/tests/verify_http.py` | `596cc1a1d318` | Reviewed/fixed: typed probe reports and exact lowercase 32-hex IDs reject forwarded valid caller IDs; headers include dummy authorization/cookie markers to verify non-emission. Native health/season/error bodies validate strictly, missing-route body remains exact native output, nonempty/current season is enforced, IDs are unique and streaming bytes/interruption stay exact. No import resource startup. |
| `backend/src/app/shared/observability/tests/verify_logs.py` | `c07777b3e39b` | Reviewed/fixed: captured events/reports validate through typed native boundaries, with exact IDs, level names, per-event severities, mode thresholds and no orphan/duplicate errors. Service ready/stopped stay INFO and request errors ERROR. Correlation count now reports actual logged IDs: five at INFO with health suppressed, six at DEBUG. Local file reads/logging remain main-owned. |
| `backend/src/app/shared/observability/util.py` | `72ebc71f109f` | Reviewed/fixed: narrow metadata guards contain BaseException from untrusted attribute access only. Missing/unreadable metadata marks exception snapshots truncated; ordinary application cancellation/interrupt remains owned by the caller. Scope and native route extraction remain request-local. |
| `backend/src/app/shared/smoke.py` | `6aca1c758286` | Reviewed: shared explicit payload predicates and typed operational exception fields; raw response/body values are failure data, not emitted diagnostic fields. No transport effects or state. |
| `backend/src/app/shared/tests/__init__.py` | `bb3c948c925e` | Reviewed: module docstring only; no executable behavior. |
| `backend/src/app/shared/tests/entrypoints.py` | `6d2ae81cf173` | Reviewed/fixed: source roots derive from absolute module-file metadata without redundant filesystem resolution at import. AST import traversal uses independent guards and explicit None checks. Directory scans occur only in explicit inspection calls; supported-module discovery now runs through pytest collection rather than a module decorator. |
| `backend/src/app/shared/tests/fakes.py` | `94e29a9f0efa` | Re-reviewed: ProcessFieldObservation and ProcessOutputObservation name finished process, constrained logging field and optional-by-shape output path concerns without positional bundles. Existing command/module bindings and native observation buffers remain fixture-owned, with no import-time processes or resources. |
| `backend/src/app/shared/tests/migrations.py` | `3f1d0d69d483` | Re-reviewed/fixed: pure metadata import and explicit source/subprocess actions remain. A frozen migration-database adapter borrows its admin engine; its context owns creation/drop through production resource ownership, always disposes on setup/body/cleanup failure and preserves primary errors/cancellation through drop failure. PostgreSQL AUTOCOMMIT remains explicit for CREATE/DROP DATABASE. |
| `backend/src/app/shared/tests/python_rules.py` | `b1d328f47d4c` | Reviewed: frozen source/rule/line scenario values contain only immutable strings/tuples and refer to the canonical Rule enum; no executable source loading, mutable state or import I/O. |
| `backend/src/app/shared/tests/resources.py` | `28241707183a` | Re-reviewed/fixed: generic frozen TeamStintQueryScenario binds the real callable Protocol to its owned fake connection. TeamStintQueryProbe retains immutable count descriptions and local call observations, returns fresh reports and is initially falsy. Existing native cleanup/session/transaction probes remain unchanged and excluded from artifacts. |
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
| `ml/src/ml/tests/fakes.py` | `6aedb7142456` | Re-reviewed/fixed: frozen named metric, expected-failure, metadata and temporal scenario bindings replace positional collaborator bundles. Typed finite mode/context aliases constrain the actual boundary attributes. Native dict/DataFrame/model buffers belong to one fixture; these records do not claim their graphs are immutable domain values. Existing borrowed-reader/resource ownership remains unchanged. |
| `ml/src/ml/tests/fixtures.py` | `2d449ca1f3d4` | Reviewed: function-scoped scenario generation, local mutable construction and named row alias; no shared dataframe construction or external I/O at import. |
| `ml/src/ml/tests/strategies.py` | `349bc88e5bf0` | Reviewed/fixed: each generated MetricScenario owns independent current/baseline/zero-tolerance dictionaries from the same finite value. Enum-derived string-compatible keys retain metric semantics; no shared mutable examples, imports with resource construction or hidden I/O. |
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
| `tests/backend/conftest.py` | `57e1ff60d75a` | Reviewed: immutable explicit backend concept fixture-plugin manifest only; no direct fixture construction, environment changes or I/O at import. |
| `tests/backend/test_alembic_logging.py` | `bd32416d778c` | Reviewed/fixed: programmatic host logging/configuration is explicit main-owned with native ExitStack stream/handler cleanup and host attachment removal. The library call still retains actual runtime/framework/cancellation identity and host snapshot. Invalid-setting process/field observations are named frozen values; all native offline/online status, SQL/stdout, revision, settings-before-connection and safe diagnostic assertions remain unchanged. |
| `tests/backend/test_api.py` | `684d40a80a1e` | Reviewed/fixed: native database failure is created afresh inside its indirect fixture from an immutable marker; expected error-detail examples are JSON descriptions decoded into fresh fixture values. Native TestClient/fake repository still verifies all public routes, camelCase, health, validation, CORS and exact public envelopes without runtime setup in imports. |
| `tests/backend/test_api_logging.py` | `c149eeee0b9f` | Reviewed/fixed: HTTP/streaming/preflight observations retain named native response/app/error/record fields; expected statuses, formatter and streaming caplog/client work are fixture-owned. The fresh host program now uses explicit main/module guard and ExitStack ownership for streams/handlers, removing borrowed root/host attachments before closing them. Original CORS/method/error/streaming/correlation, single-safe-stream and host-preservation assertions remain intact. |
| `tests/backend/test_api_service.py` | `ba6203fe8e19` | Reviewed/fixed: service/mode collaborator tuples are frozen ServiceScenario values; mutable search/comparison input lists are fresh narrow class fixtures. Existing PlayerQuery/row arrangement and all service, visibility, null/zero, stats/history/projection, contract/cap and overview/search branches retain their assertions. |
| `tests/backend/test_capspace.py` | `14e22e1d5fd4` | Re-reviewed: profile module references target canonical repository.http, so native retry sleep and wrap-through parser instrumentation affect actual execution. Complete executable AST and all identities/money/contract/reconciliation/metric assertions are unchanged. Legacy reporting/options compatibility imports remain covered. |
| `tests/backend/test_capspace_postgres_integration.py` | `06f969acbbbb` | Reviewed/fixed: preview result and before/after counts are captured in the fixture before conflict SQL setup; the body retains preview nonmutation plus actual apply/conflict/native-row assertions. Guarded shared engines and exact trusted-contract, gap/idempotence, ambiguity and write-then-fail rollback behavior remain unchanged. The deliberate partial-write fault double stays source-only. |
| `tests/backend/test_cli_contracts.py` | `5cdec01eb3dc` | Re-reviewed: command scenarios target the public render_schema_text seam. Immutable argv/summary descriptions, fresh fixture inputs, named command/mode observations and native main calls retain exact help/usage-before-work, stdout/error counts, selected historical use case, repair order and exit semantics. |
| `tests/backend/test_command_cancellation.py` | `e02cc175119a` | Re-reviewed/fixed: the bounded generated process now constructs native failures and installs the public schema seam inside main, returns the actual command exit and has a module guard. INFO/DEBUG, JSON/text, cancellation/SIGINT exits, approved command hook and safe repeated cleanup diagnostics retain their assertions. Source-only fault-double disposition remains separate. |
| `tests/backend/test_command_logging.py` | `73ccda38ee38` | Re-reviewed: generated OpenAPI main targets the public render_schema_text seam. Existing explicit main/module guards, frozen process/output observations, bounded real subprocesses, operational/ML modes, exact stdout/invocation/error and invalid-before-work checks remain. |
| `tests/backend/test_config.py` | `7624d1154587` | Reviewed: fixture-owned explicit environment mappings cover scoped URL precedence, escaped components, required values, pool defaults and CORS normalization. No real secrets, database connections, environment mutation or imports with configuration I/O; native expected values are fixed assertions. |
| `tests/backend/test_container_smoke.py` | `02fdc5a44940` | Reviewed: native HTTPError/BytesIO fixtures cover handled status, invalid bytes, read/close failures, cancellation, interruption and successful/decode-failed responses; no real network. Readiness and contract specimens are read-only, observations are fixture-owned. |
| `tests/backend/test_contract_domain.py` | `a992295230c4` | Reviewed: saved HTML fixtures create fresh contracts/documents; mutation is the tested act proving detached nested snapshots, tuple season serialization and legacy money/team/clause/ELC/slide contracts. No shared mutable decorator input or import-time resource work. |
| `tests/backend/test_contract_lifecycle.py` | `0c829e9df5f7` | Re-reviewed: active repository/service and native profile types import canonical role owners. Complete executable AST and existing fixture-owned snapshot, session, worker, batch/failure, falsy repository and resource-ownership checks are unchanged. |
| `tests/backend/test_contract_lifecycle_postgres.py` | `5101b0b3147f` | Re-reviewed: the real PostgreSQL resource test explicitly narrows the abstract run to PostgresIngestionRun before inspecting native closed handles. Actual lock overlap/reacquisition and succeeded/cancelled states remain. Disposable fixture/cursor guards, batch resume, preview nonmutation, conflict and missing-ID checks retain their behavior. |
| `tests/backend/test_contract_parsing.py` | `b542227cc1ee` | Re-reviewed: native profile references target canonical repository.http. Complete executable AST is unchanged: generated exact amount/season behavior, typed parse failures, snapshot isolation, redirect/identity and explicit page-shape cases retain their original assertions. |
| `tests/backend/test_database_cleanup.py` | `d73d74beefad` | Re-reviewed/fixed: two reversed team-stint ranges fail against the previous resource-acquisition order and pass with typed first/last fields and zero cursor events. Existing native cursor, transaction, engine, request-session and roster/source fault cases retain their original primary/cause/close-order assertions. |
| `tests/backend/test_database_transactions.py` | `a720ac970200` | Reviewed/fixed: disposable table setup/drop use separate production transactions and guarded cursors rather than a raw connection spanning fixture yield. Native commit/rollback and connection-close behavior plus exactly one contextual event are asserted. Deliberate in-transaction failure is the act needed to verify rollback, not a runtime policy implementation. |
| `tests/backend/test_historical_options.py` | `6b5661805392` | Reviewed: frozen option/limit fixtures verify canonical defaults and actual compatibility exports, inclusive boundaries, mutation rejection and caller overrides. Parser Namespace is intentionally inspected as parser output, not passed through an application main boundary. |
| `tests/backend/test_ingestion.py` | `c445e252289a` | Re-reviewed/fixed: immutable expected pairs produce fresh dictionaries, native command failures are constructed per fixture, invalid row and ambiguous identity SQL arrangement belongs to fixtures, and retained stages/results have named frozen bindings. Original precondition assertions, native parser actions, deduplication/idempotence, typed values, identity, retained rows, tracking/locks, rollback and roster transaction checks remain. Disposable Dev connections retain production ownership; SQL assertions inspect actual results. |
| `tests/backend/test_ingestion_logging.py` | `184551c0dec6` | Re-reviewed: source client imports canonical repository.http. Complete executable AST is unchanged. Safe durable context/counts, real native retry observation, concurrent worker identity, retained snapshots and existing cleanup assertions remain; native capture buffers are fixture-owned. |
| `tests/backend/test_lifecycle_logging.py` | `0d2a15f72f09` | Re-reviewed/fixed: no-false-stopped assertions now inspect retained setup-phase records, with a positive ready-count control for successful startup. The preceding call-phase capture accepted eight deliberately false stopped events; current observations reject all eight. Native protocol failure/identity/severity/bounds and context-owned fixture cleanup assertions remain intact; prior green capture evidence alone did not prove the stopped-event property. |
| `tests/backend/test_logging_policy.py` | `794138dce27d` | Reviewed/fixed: complete generated formatter/record inputs replace Hypothesis setup in the body, preserving nonempty Unicode secrets and both output formats. Normalized/invalid settings mappings and hostile formatter construction are fixture-owned with immutable parameter descriptions. Existing rendering limits, native metadata faults, sink behavior, snapshot mutation and real-capture verifier assertions remain intact. |
| `tests/backend/test_logging_startup.py` | `fb48149ba858` | Re-reviewed/fixed: generated process mains use module guards/shared exit codes; native ExitStack/closing own captures and handlers, and the shared SQLite guard owns fallback cleanup before session construction. Actual fresh-process failure/cancellation proves disposal once and original identity. The existing host snapshot/idempotence, deferred real Vercel export, repeated approved hook, exact conflict/invalid-setting leaves and task/subprocess timeouts remain. |
| `tests/backend/test_migration_tooling.py` | `c3ebfdb6090b` | Reviewed/fixed: disposable migration admin/temporary engines now use guarded ownership, including setup before yield; six fault cases retain primary identity/cancellation and always dispose. Unversioned schema setup belongs to a fixture; expected payloads/URLs are immutable descriptions and native HTTP responses are fresh fixture-owned values. Real lifecycle keeps checksum, offline/online upgrade, idempotence, downgrade, schema and reference contracts. Historical private revision calls verify its exact frozen compatibility boundary. |
| `tests/backend/test_openapi_contract.py` | `4d4c54f96fc4` | Reviewed/fixed: root derives from module-file metadata without filesystem work during import; committed schema input belongs to a fixture. Actual schema generation remains the act. All 18 public operations retain success/shared error refs and no native 422 public envelope. |
| `tests/backend/test_operational_errors.py` | `52f5c7df57a5` | Re-reviewed/fixed: two real repair calls use an initially falsy injected query satisfying the runtime Protocol, rejecting default queries and verifying exact bounds, returned counts/applied flag and commit-or-rollback followed by close. Fresh count descriptions, options and native probes are fixture-owned. Existing structured configuration, smoke and operational failure checks remain unchanged. |
| `tests/backend/test_postgres_integration.py` | `3e19bfda48a7` | Reviewed/fixed: expected ordering examples are immutable tuples and fresh search/comparison lists belong to fixtures. PostgreSQL/Session ownership, PlayerQuery and SQL input arrangement remain fixture-owned. Totals/current-team precedence, model/replacement semantics, calendar visibility, cap, null/zero behavior, pagination and bound injection assertions retain their contracts. |
| `tests/backend/test_python_rules.py` | `e5fab98155b0` | Reviewed: immutable SyntaxCase examples protect exact forbidden syntax locations and deliberate semantic-review gaps without executing source. Temporary source trees and bounded Git inventory are fixture-owned; command tests verify fail-closed errors and safe relative diagnostics. Forbidden syntax exists only as quoted parser input, not executable test implementation. |
| `tests/backend/test_request_logging.py` | `fb980fbc6cd8` | Reviewed/fixed: native propagated-host LogRecord and its actual setup-phase records belong to one fixture observation. Frozen concurrent app/scope/transport/state bindings preserve the deliberate shared-state alias test. Native formatter/filter construction is fixture-owned; distinct reported-filter instances still prove consumption survives instance changes. Streaming/cancellation identity, health suppression, safe metadata and correlated interleaving assertions retain their scope. |
| `tests/backend/test_roster_status_service.py` | `bf45325f1c83` | Reviewed/fixed: malformed/empty-discovery payload examples are immutable JSON descriptions decoded into fresh fixture state; transport query/client construction is fixture-owned. Fake repositories/feeds and native JSON/JSONP/HTTPError probes retain precedence, conservative identity, incompleteness, request/timeout/close and primary-error assertions. Immutable player/feed argument tuples are boundary input values, not resource collaborator bundles. |
| `tests/backend/test_runtime_resources.py` | `8fcba58d9b30` | Re-reviewed: the fresh-import guard now calls public render_schema_text; dotenv/database construction remains forbidden during imports/schema generation. Existing guarded engine/session fixtures, setup/close fault identity/cause, environment preservation and fresh HTTP input scenarios remain unchanged. |
| `tests/backend/test_source_identity.py` | `5b6b0e816a64` | Reviewed/fixed: quality report, bounds and expected typed violation are a frozen named scenario; generated normalization and original-hash/deduplication operations remain the tested acts. Original equivalent numeric identity space, last-original-snapshot behavior, row-count-before-ratio precedence and typed context assertions are unchanged. |
| `tests/backend/test_source_identity_postgres.py` | `cf78af484673` | Reviewed/fixed: source repositories are a frozen named holder and share a fixture-bound transaction factory with explicit disposable Dev settings. Setup and verification cursors use the primary-preserving guard. Native persistence still proves player/source identity, repeated alias idempotence, skipped counts and original snapshot hashes for both kinds. |
| `tests/backend/test_source_ingestion.py` | `82ace137f777` | Re-reviewed/fixed: 96 native owner/entry-or-body/primary/cleanup combinations reproduce 63 failures against the preceding exact owner definitions and all pass after the guard. Actual native Session close, source/profile entry, cause/identity, one close, secondary notes and sole cleanup propagation remain explicit assertions. BaseException capture prevents unexpected injected interrupt from aborting diagnosis while exact identity assertions still fail closed. All 68 prior IDs and 18 setup regressions remain; patches restore before fallback Session cleanup. |
| `tests/backend/test_supported_entrypoints.py` | `111ebffb8ff2` | Re-reviewed: four fresh-module guards now cover inspection helpers plus OpenAPI/ML path tests with resolution/scans/reads forbidden during import. Explicit compilation/archive/module inspection and bounded fresh interpreters retain the supported executable inventory. Collection-time discovery stays explicit. |
| `tests/backend/test_transaction_logging.py` | `b57666912f9e` | Re-reviewed: current captured-event logic already uses explicit counts and boolean any predicates; no remaining container-truthiness finding was present. Fixture-owned resource failures retain real commit/rollback/close ordering, primary/cancellation, mode/format thresholds and secondary notes. Handler and native record buffers are local probes. |
| `tests/conftest.py` | `2084ef23201a` | Reviewed: collection enforces integration ownership before work and otherwise applies unit isolation. Native sockets are guarded only inside unit fixtures; integration settings are scoped to a disposable named Dev database and restored by monkeypatch. Session sklearn import intentionally initializes native runtime before collection; no database connection or source network request occurs at import. |
| `tests/ml/__init__.py` | `e3b0c44298fc` | Reviewed: empty package/placeholder; no executable behavior. |
| `tests/ml/conftest.py` | `3a7bc20eebd4` | Reviewed: immutable explicit ML fixture-plugin manifest only; no direct setup or import-time resource acquisition. |
| `tests/ml/test_boundaries.py` | `5d4dfa12759d` | Reviewed: fixtures own settings/resources/arrays and immutable class column metadata; borrowed/preloaded reader tests, snapshot mutation and artifact round trips preserve input ownership. Arrangement removed from invalid-shape acts; normal imports replace inline module discovery. |
| `tests/ml/test_features.py` | `fcf5144a399d` | Reviewed: fixture-owned scenarios, named percentile regressions, independent position-code contract, input/index preservation and meaningful numerical/grain/leakage assertions. No external resources. |
| `tests/ml/test_logging.py` | `f4a6ef8bdcdb` | Reviewed/fixed: prediction feature-column/frame arrangement now belongs to a fixture. Real fixture-owned models/data/artifacts still compare native predictions, metadata and output rows; split/metric/write diagnostics preserve mode, partial-write and secret-exclusion behavior. Data/model buffers remain local native resources. |
| `tests/ml/test_metadata.py` | `4f825c6594a0` | Reviewed/fixed: mutable dictionary/list decorator templates are immutable pair/tuple descriptions, with fresh native metadata/frame/metric values in fixtures. Named metric/temporal/metadata expected-failure scenarios retain exact context and typed leaves. Baseline serialized text is fixture-arranged; mutation remains the act proving detached immutable metadata. Finite generated equal-metric behavior and public string-key semantics remain covered. |
| `tests/ml/test_paths.py` | `e6b9c2237a02` | Reviewed/fixed: source destination uses module-file metadata without import-time resolution. Fixture-owned environment/cwd scenarios verify default artifact discovery independently of checkout cwd and explicit external destinations; no import-time resource creation. |
| `tests/ml/test_valuation.py` | `cbe019e4ed47` | Reviewed/fixed: invalid NumPy arrays are created in fixtures from immutable tuples; metric descriptions become fresh dictionaries in named scenarios. Model feature inputs, artifact path, baselines and tolerances belong to fixtures. Native deterministic training, temporal leakage/zero target, safe prediction, serialization round-trip, metric direction and metadata boundaries retain their assertions. |

# Core data pipelines (Phase 3)

`app.jobs.core_operations.core_operations()` registers the eight core operations
used by the existing independent job and database-setup entrypoints. Collection,
normalization, identity checks, validation, provenance, and atomic uploads use the
same execution path in initial, refresh, backfill, and validation modes.

| Job | Source and behavior |
| --- | --- |
| `teams_seasons` | NHL teams, franchises, seasons, historical team participation, and current standings. Current standings include teams before their first game; historical names remain on team-season records. |
| `player_profiles` | NHL biographies discovered from regular-season/playoff participation, current and historical rosters, explicit dependent-source NHL IDs, and completed-game boxscore participation. Includes retired players. |
| `team_rosters` | NHL roster lists, undated team-season memberships, and dated current roster observations. Missing profiles are held for discovery/reprocessing. |
| `source_id_mappings` | NHL identities, NHL-ID-addressed Cap Space profiles, and supplied cross-ID/manual decisions. Conflicting mappings are held; names do not establish player identity. |
| `basic_stats` | NHL skater/goalie summary feeds. Independent TOTAL and TEAM queries retain traded-player grains and regular-season/playoff distinctions. |
| `contracts` | Cap Space agreement tables. An explicitly mapped, NHL-ID-verified CapWages profile is eligible for fallback when the primary cannot cover a player. |
| `transactions` | Current/recent USA Today NHL transactions from the page's embedded structured payload. Stable IDs support duplicate detection and versioned corrections. |
| `roster_reconciliation` | Accepted NHL roster observations, typed transaction evidence, and dated manual overrides. Uncertain changes are held. |

Games, MoneyPuck, and EDGE are registered separately through
[the Phase 4 registry](game-tracking-pipelines.md). [Phase 6 infrastructure](local-persistence-datasets.md)
provides local PostgreSQL persistence and explicitly configured dataset builds.
AWS acceptance remains Phase 9. Recurring
workflows are created in Phase 7, verified live in Phase 10, and enabled in
production in Phase 11.

## Offline usage

From the repository root, with the development dependencies installed:

```bash
PYTHONPATH=backend python3 -m app.database_setup.run_setup \
  --environment dev --current-season 2026 --first-season 2025 \
  --jobs teams_seasons player_profiles team_rosters source_id_mappings \
         basic_stats contracts transactions roster_reconciliation \
  --runtime tests.core_source_fixtures:create_runtime --validation-only

PYTHONPATH=backend python3 -m pytest backend/tests/test_core_sources.py --no-cov
```

The fixture runtime supports `dev` only, uses an in-memory test store and injected
HTTP responses, and makes no network requests. Each CLI invocation starts a new
fixture store. Tests reuse a store to verify initial population, independent
refreshes, corrections, rollback, and reruns. This demonstrates source-to-upload
contract behavior, not durable persistence or full live-source coverage.

## Infrastructure integration

Supply an `Executor` with a conforming, environment-verified `DataStore`, this
registry, and a `SourceClient` configured for `nhl`, `capspace`, `usatoday`, and
`capwages` if fallback is enabled. Set independent source request policies through
`RequestPolicy`; the existing client enforces timeouts, retries, response limits,
request budgets, and rate limits. Imports do not create connections or requests.

```python
from app.jobs.core_operations import core_operations, Discovery, MappingCandidate
from app.jobs.sources.transactions import TransactionPolicy
from app.jobs.shared.execution import Executor
from app.jobs.shared.source_requests import RequestPolicy, SourceClient

operations = core_operations(
    discovery=Discovery(player_ids=discovered_nhl_ids),
    mappings=reviewed_mapping_candidates,
    transaction_policy=TransactionPolicy(recent_days=3),
)
executor = Executor(
    configured_store, operations, target_environment=verified_environment,
    client=SourceClient({source: RequestPolicy() for source in
                         ("nhl", "capspace", "capwages", "usatoday")}),
)
```

The store, environment verification, discovered IDs, and reviewed mapping inputs
in this example are supplied by infrastructure. No production runtime is bundled.
Resolve the current season before constructing the existing `JobConfig`; the
adapters verify requested NHL seasons instead of hard-coding the latest year.

## Source and identity policy

NHL is the selected basic-statistics source for Phase 3. Cap Space is the primary
contract source. Preserve raw source fields and exact USD cents; absent salary,
bonus, or statistical values remain null. A rounded skater TOI-per-game value is
not multiplied into a purported exact total. NHL goalie total TOI uses seconds.
Published ratios remain ratios. No aggregate totals are added to team totals.

Existing canonical IDs are reused by their unique NHL IDs. New NHL identities use
their native numeric IDs only when those canonical keys are unoccupied; a
collision requires identity-service/manual review. USA Today IDs are a separate
namespace. `MappingCandidate` supplies a source ID, entity kind, verified NHL ID,
and retained evidence text. Infrastructure owns verification of that crosswalk or
manual decision. An unmapped vendor ID produces review issues even if its name
matches a known player. Reassignment of an existing mapping is never automatic.

Memberships represent positive team-season roster evidence with unknown episode
dates. Repeated roster observations do not invent transfers, removals, or separate
return episodes. AHL rosters are not collected. Descriptions mentioning an AHL
team remain source text and do not drive status or financial rules.

## Contracts and coverage

Contracts require accepted membership or game-type-filtered statistical
participation in the requested range. This includes retired players and makes
missing player-season salary coverage visible. Missing required seasons fail the
run; source access alone never proves complete salary coverage.

Agreement identity uses a published contract ID or NHL player/signing-date/start
season combination, independent of mutable financial values. Tables must contain
contiguous distinct covered seasons and valid exact money. Nominal terms altered
by explicit entry-level slide rows are retained alongside their covered span.
Buyout/termination charge sections are excluded from agreement salary terms.

Logical contract version 2 allows an agreement to begin before 2008 while its
uploaded salary terms still obey the 2008 coverage baseline. The full agreement
span and signing date remain intact. Start-season references are required when
the start is 2008 or later; prebaseline starts are metadata, not collected seasons.
Contract-derived season references, including published future years, are
supporting outputs with reserved write scopes. Existing season metadata is
preserved. A narrower refresh can still validate its agreement's full season span.

Fallback requires an accepted CapWages player mapping and a matching embedded NHL
ID. Partial primary coverage and overlapping competing agreements require review;
the adapter does not silently merge sources or replace an existing agreement with
a competing identity. Contract-source schemas and fallback availability still
require live coverage auditing before Phase 9 AWS population claims.

## Transactions and contract-refresh requests

The runtime policy defaults to a three-day recent window. Correction lookback can
widen it to at most 31 days. No historical-season or archive requests are made,
including initial setup. Existing entrypoint guards reject transaction backfills.

The page's source cursor must prove that its frontier is strictly older than the
requested window, or the source must explicitly declare enumeration complete.
A same-day boundary can omit events; an incomplete/truncated window fails without
advancing progress. Larger windows during busy periods may need a separately
verified pagination implementation; narrowing a window is a scope change, not
evidence that a larger requested window was complete.

Identical IDs/payloads are deduplicated. Conflicting duplicate payloads require
distinct explicit source update times or review. Corrections from subsequent
fetches retain prior accepted revisions. Every participant and nonempty team ID
must resolve through the USA Today mappings; free text never supplies identities.

Signing and extension facts include immutable `refresh_requests` in the same
atomic batch. Each request binds the source event ID, raw revision digest, and
canonical player. Reruns retain the request; a correction creates a new request.
A transaction with all participant requests must fit one batch or the run fails
before committing. No scheduler is activated. Phase 7 workflow consumers must coalesce
requests and check their triggering revision is still applicable before dispatch.

## Roster precedence and recovery

One currently effective manual override takes precedence. Overlapping overrides
require review; expired overrides allow recomputation from accepted source facts.
Otherwise, use fresh positive NHL roster observations and accepted typed
transactions ordered by event date. Collection order cannot decide same-day
conflicting events. Multi-player trades require explicit `to_team`/`from_team`
participant directions before projecting each player's team.

LTIR and assignments remain supported until an explicit activation/recall event;
a newer roster fetch alone does not clear them. Generic injured reserve,
suspension, unknown transitions, missing teams, or absent/stale roster evidence
cannot invent a supported status. Valid raw observations and review issues are
retained while the affected batch and checkpoint are held. Missing players from
an incomplete response are never treated as removals.

Collectors use bounded batches and fingerprint their source enumeration. Resume
continues a committed prefix only while the enumeration remains identical;
otherwise rerun without `--resume` to reprocess corrections. Validation-only setup
merges candidates over one accepted snapshot, retains temporary provenance for
downstream reconciliation, and performs no writes.

## Verification and remaining gates

The focused tests cover source parsing, valid/empty/malformed/incomplete responses,
unresolved identities and replay, current/historical scope, exact units, retired
and game-participation discovery, duplicates/corrections, multiple participants,
source failures, override expiration, ambiguous trades, out-of-order events,
source-to-upload rollback, and validation-only setup. Recorded source-format
samples are described in the fixture README.

Final required/optional scope acceptance, live crosswalk review, measured
historical salary/source coverage, database integration, durable concurrency,
consumer query mappings, schedules, and cutover remain their existing release
gates. The Phase 3 fixtures do not establish those later guarantees.

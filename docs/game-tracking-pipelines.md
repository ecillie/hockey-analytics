# Game, MoneyPuck, and EDGE pipelines (Phase 4)

`app.jobs.game_data_operations.game_data_operations()` registers five independent
operations. Existing setup, backfill, validation-only, and refresh entrypoints
use the same source parsing, identity checks, validation, and atomic upload path.
`source_operations()` composes these with the Phase 3 registry; `datasets` remains
unregistered. Imports make no requests and open no database connections.

| Job | Collection and declared checks |
| --- | --- |
| `game_schedule` | NHL club-season schedules from accepted historical team-season references. Deduplicate the same game across clubs; reject conflicting facts, unsupported states, missing completed scores, and wrong seasons. Exclude preseason. |
| `game_details` | Accepted completed games only. Verify game/season/type/team identity and scores; validate boxscore enumeration, available goal totals, exact TOI, goalie totals, event IDs, source order, clocks, and coordinate pairs. |
| `moneypuck_stats` | Published skater, goalie, team, and line CSVs for each requested season and regular/playoff feed. Preserve source situations, TEAM/TOTAL grains, native NHL player IDs, sorted line members, source xG definitions, and exact count fields. |
| `moneypuck_shots` | Published per-season ZIP archives. Stream one bounded CSV, exclude preseason, resolve accepted games, validate shot IDs, outcome/goal flags, xG probabilities, and paired raw or arena-adjusted coordinates. Blocked attempts are excluded by the source. |
| `edge` | NHL participation enumerates team/skater/goalie summary eligibility. Validate each requested detail identity and available season/type manifest. Retain dated source measurements and breakdowns with explicit units. Required unavailable summaries fail visibly. Optional audited game/event samples remain labelled limited. |

## Offline execution

From the repository root:

```bash
PYTHONPATH=backend python3 -m app.database_setup.run_setup \
  --environment dev --current-season 2026 --first-season 2026 \
  --jobs game_schedule game_details moneypuck_stats moneypuck_shots edge \
  --runtime tests.game_data_source_fixtures:create_runtime --validation-only

PYTHONPATH=backend python3 -m app.jobs.game_schedule \
  --environment dev --current-season 2026 --mode refresh \
  --runtime tests.game_data_source_fixtures:create_runtime

PYTHONPATH=backend python3 -m pytest backend/tests/test_game_data_sources.py --no-cov
```

The fixture runtime seeds accepted development references and makes no network
requests. A new invocation starts a fresh in-memory store. Independent details
and shot commands require accepted schedules; the setup demonstration establishes those
first. The standalone schedule, statistics, and EDGE jobs use seeded references.
The tests reuse a store for dependent jobs, correction refreshes, failure recovery, and reruns. No production persistence
or full live-source coverage is established by these demonstrations.

## Runtime integration and scope

```python
from app.jobs.core_operations import core_operations
from app.jobs.game_data_operations import game_data_operations, DownloadPolicy
from app.jobs.shared.execution import Executor
from app.jobs.shared.source_requests import RequestPolicy, SourceClient

operations = {
    **core_operations(),
    **game_data_operations(download_policy=DownloadPolicy(
        max_uncompressed_bytes=512_000_000, max_rows=300000)),
}
client = SourceClient({
    "nhl": RequestPolicy(),
    "moneypuck": RequestPolicy(max_response_bytes=100_000_000),
    # Add the independent Cap Space/CapWages/USA Today source policies when
    # the runtime also invokes those core operations.
})
executor = Executor(verified_store, operations,
                    target_environment=verified_environment, client=client)
```

Infrastructure supplies the store, environment verification, and runtime factory.
MoneyPuck's request policy also governs its catalogue-linked `peter-tanner.com`
archives. HTTP timeouts, request budgets, bounded retries, byte limits, and source
rate limits remain independent. Redirects do not bypass those policies.

NHL/MoneyPuck history starts at 2008; EDGE starts at 2021. Configuration requires
runtime-resolved upper bounds and only game types 2/3. Setup completes schedule
producers before dependent game/shot jobs. Historical team-season abbreviations
resolve MoneyPuck teams; documented legacy abbreviations `N.J`, `L.A`, `S.J`, and
`T.B` map to their NHL abbreviations. Unknown or ambiguous teams require review.
Names never establish a player identity, and canonical IDs need not equal NHL IDs.

## Corrections, identity discovery, and recovery

Details always collect unprocessed completed games, including older ones. Refresh
rechecks already processed games starting at run time minus
`correction_lookback_days`; zero skips older processed games. Initial/backfill
modes examine every selected completed game. Refresh schedules first when scores
or states change. TOI uses explicit MM:SS seconds; missing values stay null.
Shootout scores can contain the additional winning goal, which is not a skater
goal. Clock checks distinguish regular-season overtime from playoff overtime.

The downloaded shot archive is reused across streaming passes; its row and
expanded-size limits prevent unbounded decompression. Game details freeze the
requested enumeration in a temporary spool before uploads, holding one game and
one batch in memory. The spool uses disk above 1 MB and rejects more than 2 GB or
more records than the configured batch capacity. It is deleted on completion or
failure. Source enumeration fingerprints prevent resuming a changed feed; rerun
without resume to reprocess corrections. Atomic records/provenance/checkpoints
use the existing executor, including rollback and exact upload retries.

Unknown players hold a batch and retain its raw observations and review issues.
NHL boxscores/events, MoneyPuck players/line members/shooters, and EDGE entity
observations explicitly retain their native NHL IDs. The existing `player_profiles`
operation automatically includes these IDs in discovery, fetches their NHL
biographies, and preserves collision safeguards. Run it successfully, then replay
the held dependent job. `missing_player_discovery(ctx)` also exposes the discovered
IDs for infrastructure. No dependent job writes profiles outside its declared
outputs. Unresolved teams and canonical-ID collisions still require reference or
mapping review.

Corrections retain the accepted record's key and prior revisions. A source removing
an accepted NHL event or MoneyPuck shot fails for review: the logical contract has
no deletion/tombstone operation. It must not report a successful refresh that leaves
a known removed event unaddressed. Database-specific removal handling remains a
contract/infrastructure decision before production population.

## EDGE metric and sample policy

The default detail adapters recognize source-labelled imperial/metric speed and
distance measurements, documented count fields, and named ratio fields. Ratios
remain 0–1, speeds/distances retain their source units, and breakdowns retain source
paths. Unknown measurements remain in raw provenance and appear in coverage
reports. A response with no recognized measurement fails instead of guessing units
or fabricating zeroes. Fetch failures, wrong entity/season/type responses, and
required scopes missing from an eligibility manifest do not count as coverage.

No default detail response establishes independently enumerated game or event
history. Both optional families report `unavailable` when no audited feed is
configured. Infrastructure may supply `SampleFeed` definitions through
`game_data_operations(edge_sample_feeds=...)`. Each definition supplies an NHL EDGE
URL template, entity identity, source record path, stable game/event ID field, and
explicit `MetricField` paths, units, and definitions. The adapter validates source
identity/season/type, game references, duplicates, and measurements. Optional HTTP
404 responses report unavailable; other errors fail. A fetched recent-game or
selected-event feed always reports `limited`, including empty lists. Those samples
never become complete historical tracking events. No speculative sample endpoint
or manufactured event identity is bundled.

## Coverage evidence and verification limits

CLI JSON and `RunReport.source_coverage` expose requested seasons/types, enumerated
source counts, expected populations when independently provided, statuses, and
limitations. Terminal run scope persists this evidence, including empty and
unavailable feeds; record provenance retains its feed evidence and transformation
version `game-data-sources-1`. Enumeration counts are not accepted database counts.
CSV/club feeds leave independent expected population unknown. Continue to use the
separate `validate_setup` gate with independently established coverage observations
before claiming complete population.

NHL play-by-play reports observed event types and the number of complete coordinate
pairs per game. Available historical plays are labelled limited, even when their
endpoint is fully enumerated. MoneyPuck shots explicitly exclude blocked attempts;
no shot-map or shooting summaries are derived. EDGE observations describe dated
summaries or sampled feeds, not exhaustive tracking-event history.

Verification on 2026-10-13: 79 focused source checks pass; the configured
backend/ML suite passes with 593 passed, 30 skipped, and 74.81% branch-aware
coverage. The validation-only CLI completes all five jobs, the standalone schedule
CLI succeeds, and the committed OpenAPI check passes.

The focused offline tests cover all five jobs, requested scope, historical
MoneyPuck field formats, source failure, malformed/duplicate responses, measurements
and totals, traded-player/situation distinctions, missing identities and automatic
discovery/replay, corrections and removed records, streamed archive limits, atomic
interruption/resume, sampled EDGE records, explicit unavailable feeds, persisted
coverage evidence, and validation-only setup.

Fresh NHL/MoneyPuck download probes during this implementation returned HTTP 403.
The source catalogue was readable, but those probes did not verify current JSON/CSV
payloads. NHL/EDGE response-shape tests are illustrative offline fixtures; 2008
MoneyPuck excerpts come from the repository's existing historical input files.
Before Phase 9 AWS population claims, audit live source schemas, complete historical
populations, EDGE field/feed availability, and current-season publication. Final
required/optional scope acceptance, durable databases/leases, consumer integration,
schedules, and cutover remain their existing later release gates.

Sources: [NHL API](https://api-web.nhle.com/),
[MoneyPuck published downloads](https://moneypuck.com/data.htm),
[NHL EDGE](https://www.nhl.com/nhl-edge/).

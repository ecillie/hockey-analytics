# Supported ingestion entrypoints

The schema-native ingestion pipeline replaces the former ORM-based `save_*`
scripts. Those scripts depend on the removed `app.models` module and are kept
under `backend/legacy_loaders/` as recovery references. They are intentionally
outside the importable application tree and are not supported entrypoints.

Supported commands, run from the repository root after `uv sync --locked --all-groups`, are:

```bash
uv run python -m app.ScriptingFiles.FullDataScript.run_all
uv run python -m app.ScriptingFiles.FullDataScript.populate_roster_status
```

`run_all` performs the full idempotent load and then refreshes roster status.
`populate_roster_status` is the supported standalone roster-status refresh.
Alembic must be at head before either command runs.

Roster synchronization uses immutable player/feed values in `roster_status/domain.py`,
validated source shapes in `schemas.py`, a transaction-injected `repository.py`,
and orchestration in `services.py`. `policy.py` preserves LTIR, NHL, then AHL
precedence; `util.py` owns name/date parsing and conservative identity matching.
The NHL/AHL adapters receive an HTTP client and frozen options. The command
boundary reads `AHL_FEED_KEY` and `AHL_SEASON_ID`; importing or constructing an
adapter does not read environment configuration or make requests. The default
HockeyTech key is the public LeagueStat web-client key.

Feed payloads must have the expected JSON or JSONP object shape. Invalid or
incomplete sources produce error results instead of an empty successful feed.
Known AHL IDs take precedence over names; new mappings require an unambiguous
normalized name and birth date. Repeated sightings with the same identity are
consolidated, while conflicting profiles for one AHL ID make the feed incomplete.

The synchronization service returns positive classifications and preserves
uncertain statuses on partial feeds. The supported command requires both feeds
to be complete: any feed failure rolls back the entire status/mapping transaction.
The separately committed ingestion run is marked failed. Adapters and core
services return diagnostics; the CLI reports the failure once.

Roster fakes and fixture plugins live in `roster_status/tests/`, with executable
tests under root `tests/backend/`. Test support is excluded from production
coverage and from the API's ingestion-free wheel and deployment artifacts.

For databases populated before season-ending team assignments were persisted,
preview and apply the idempotent set-based repair from the repository root:

```bash
DATABASE_URL=postgresql://localhost/hockey_analytics_dev \
  uv run python backend/database/backfill_team_stints.py
DATABASE_URL=postgresql://localhost/hockey_analytics_dev \
  uv run python backend/database/backfill_team_stints.py --apply
```

The remaining Python modules in this directory and `roster_status/` are
implementation modules used by those commands. Required CI imports every one
of them in a fresh interpreter and compiles the complete backend application.
## Source ingestion boundaries

`ingestion.py` remains the supported composition entrypoint. MoneyPuck, NHL
roster/statistics, and schedule work is implemented under `source_ingestion/`:

| Concern | Modules |
| --- | --- |
| MoneyPuck fetching, quality gates, advanced-stat persistence | `moneypuck/domain.py`, `moneypuck/services.py`, `moneypuck/repository.py` |
| NHL metadata, traditional statistics, roster identity linking | `nhl/domain.py`, `nhl/services.py`, `nhl/repository.py` |
| Schedule pagination and game upserts | `schedule/domain.py`, `schedule/services.py`, `schedule/repository.py` |
| Frozen values and metric layouts | `domain.py` |
| Source response validation and localized values | `schemas.py` |
| Quality policies and structured violations | `policy.py`, `errors.py` |
| Numeric, CSV, identity, and team normalization | `util.py` |
| Shared PostgreSQL identity/upsert helpers | `repository.py` |
| Retry sessions and transport protocols | `http.py` |

Services receive source clients and repositories. They finish source coverage,
required-column/value, finite-number, duplicate-ratio, row-count, and statistical
consistency checks before handing immutable snapshots to persistence. Each
PostgreSQL repository owns one stage transaction through an injected transaction
factory. A failed batch rolls back that stage. Upserts retain records absent
from a later snapshot; they do not infer deletion from absence. Existing
external-ID links and season-ending team assignments are preserved.

NHL statistics use at most six workers by default. Each job owns and closes its
HTTP session; pagination uses pages of 100 and a configurable 1,000-page limit.
Invalid totals, nonadvancing schedule dates, and empty pages before an announced
total cause validation failures. A caller-supplied session remains caller-owned
and its requests are synchronized when shared across statistics jobs. JSON and
CSV requests retain 30- and 60-second default timeouts, respectively, with four
GET retries and the existing 0.6 backoff factor and retry statuses. Frozen options
make these settings explicit and injectable.

The July 1 calendar primitive is shared with the API in `app/shared/calendar.py`.
Historical MoneyPuck/statistics ranges and the schedule's explicit season default
retain their existing meanings. `TRADEVALUE_DATA_DIR` is resolved when composing
a MoneyPuck stage, rather than during module import. Optional numeric parsing
keeps missing/unrepresentable values as missing; contract money parsing remains
separate. Typed stage summaries are flattened deliberately at the run-tracking
boundary into the existing summary keys.

The current CapWages contract refresh remains in `ingestion.py` for its later
contract phases; its shared identity and HTTP imports use the extracted helpers.
No live upstream calls are needed for verification. Source fakes and fixture
plugins live under `source_ingestion/tests/`, with executable unit and PostgreSQL
tests under root `tests/backend/`. Test support is excluded from production
coverage, and source ingestion remains outside the request-serving API wheel.

# Historical contract gap filling

The supported historical contract stage is `capspace.py`. It selects NHL
regular-season player-seasons with no `contract_seasons` coverage and resolves
the player's NHL external ID. CapSpace is queried first by NHL ID. When it has
no contract covering the missing seasons, the stage tries a bounded CapWages
profile fallback. Newer CapWages profiles must carry the same NHL ID; legacy
profiles without that field must match the canonical name and slug and have an
NHL stats season overlapping the missing-season target. Each source keeps its
own provenance. Auxiliary buyout, termination-fee, and cap-recapture table
sections are excluded from the signed contract's season rows.

Run locally after applying migrations:

```bash
ENV=dev DATABASE_URL=postgresql://... \
  uv run python -m app.ScriptingFiles.FullDataScript.capspace --dry-run
ENV=dev DATABASE_URL=postgresql://... \
  uv run python -m app.ScriptingFiles.FullDataScript.capspace --apply --nhl-id 8467514 --force
```

The loader is advisory-lock protected, source-provenanced, idempotent, and
capped at eight workers (four by default). It fetches and commits bounded
batches (100 players by default), uses PostgreSQL bulk inserts for source
snapshots and new contract-season rows, and retains prior committed batches if
a later batch fails. Override the batch size with `--batch-size`; smaller
batches reduce retry cost, while larger batches reduce transaction overhead.
Source failures retain the last-good database state. CapWages slug guesses are
bounded: a missing base slug is not followed by guaranteed-failing numbered
guesses, while a same-name identity mismatch can try `-1` through `-3`. Use
`coverage_report()` or the command's metrics to measure remaining gaps;
residual gaps can represent missing NHL IDs, profiles absent from both sources,
absent source seasons, or a reconciliation conflict. Neither source is claimed
to provide complete historical coverage.

The normal `run_all` order is current/recent contract ingestion, historical
two-source gap filling, then downstream schedule loading. The legacy contract
scripts are recovery references and are not part of this pipeline.

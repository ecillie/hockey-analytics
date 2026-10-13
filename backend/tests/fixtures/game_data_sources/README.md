# Phase 4 source fixtures

The four `2008_*.csv` files copy the first three records from the existing
MoneyPuck historical CSV inputs under `app/ScriptingFiles/data/`. They preserve
source columns, including decimal-form count values, the team's `iceTime` field,
and historical line/team abbreviations. `team.1` reflects the existing exported
input's duplicate-column spelling. No fresh download or complete historical
population is claimed. MoneyPuck publishes the catalogue and definitions at
https://moneypuck.com/data.htm.

`tests.game_data_source_fixtures` constructs illustrative NHL schedules, boxscores,
play-by-play, and EDGE details; MoneyPuck statistics and shot archives are small
synthetic fixtures with declared source meanings. These are parser/behavior
fixtures, not captured current responses or proof of live historical completeness.
Optional EDGE sample tests explicitly configure a fixture-only endpoint and
reviewed metric paths; it is not represented as a working public endpoint.

Tests combine accepted canonical references with an injected bounded HTTP client
and in-memory contract store. No credentials, real database, network requests,
recurring schedules, or production data are involved.

# Recorded public source-format samples

Captured on October 12, 2026 for repeatable parser/normalizer checks:

- `capspace_current.html`: the current contract block from
  [Cap Space's NHL-ID-addressed profile](https://cap-space.com/person/nhl:8471214).
  The HTML subtree is retained; unrelated page content is omitted.
- `usatoday_page.html`: first and last transaction rows plus cursor/count metadata
  from [USA Today's NHL transaction page](https://sportsdata.usatoday.com/hockey/nhl/transactions),
  wrapped in its observed `__NEXT_DATA__` structure. Intermediate rows and unrelated
  page data are omitted. This reduced sample is for format checks, not completeness.
- `stats.json`, `goalies.json`: two-row responses from the NHL
  [skater summary](https://api.nhle.com/stats/rest/en/skater/summary) and
  [goalie summary](https://api.nhle.com/stats/rest/en/goalie/summary) endpoints for
  season `20252026`, game type `2`, with `isAggregate=false`, `isGame=false`,
  `start=0`, `limit=2`. Their original source totals are retained.
- `teamstats.json`: the NHL
  [team summary](https://api.nhle.com/stats/rest/en/team/summary) response for the
  same season/game type with `limit=100`.

`backend/tests/core_source_fixtures.py` separately supplies a small complete,
synthetic source population and injected transport for end-to-end tests. No
routine test requires the upstream sources or treats these format samples as
evidence of full live coverage.

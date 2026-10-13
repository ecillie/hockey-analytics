"""Offline Phase 3 source runtime. Public response shapes, no database/network."""
from urllib.parse import parse_qs, urlparse
import json
import re

from app.jobs.core_operations import core_operations
from app.jobs.sources.nhl import Discovery, MappingCandidate, season_id
from app.jobs.shared.execution import Executor
from app.jobs.shared.source_requests import RequestPolicy, Response, SourceClient
from .contract_store import ContractStore
from .execution_fixtures import NOW


def transaction(source_id="sign-1", player_ids=("p1",), *, day="2026-10-11", kind="Signed", team="t10", description="Published signing"):
    row = {"id": source_id, "league": {"abbreviation": "NHL"}, "description": description,
           "date": {"full": day}, "transactionType": {"name": kind, "transactionTypeID": "1"},
           "player": {"playerID": player_ids[0], "firstName": "Fixture", "lastName": "Player"},
           "team": {"teamID": team, "abbreviation": "TOR"}, "fromTeam": {"teamID": ""}}
    if len(player_ids) > 1:
        row["players"] = [{"playerID": player_id, "role": "participant"} for player_id in player_ids]
    return row


def page(rows, *, cursor=None, num_results=None):
    data = {"props": {"pageProps": {"fallback": {"transactions": rows, "cursor": cursor,
            "numResults": len(rows) if num_results is None else num_results}}}}
    return '<html><script id="__NEXT_DATA__" type="application/json">' + json.dumps(data) + '</script></html>'


def contract_page(nhl_id, *, cap_hit="$1,000,000", first=2025, last=2027, term=None, signing_team="TOR"):
    rows = "".join(f'<tr><td>{year}-{year+1}</td><td>{cap_hit}</td><td>$800,000</td><td>$200,000</td><td></td><td>NMC</td></tr>' for year in range(first, last+1))
    identity = json.dumps({"props": {"pageProps": {"player": {"nhlId": nhl_id}}}})
    return f'''<script id="__NEXT_DATA__">{identity}</script>
    <div class="contract" data-contract-id="agreement-{nhl_id}"><strong>Standard Contract</strong>
    <table><tr><td>Total Value: $3,000,000</td><td>Seasons: {last-first+1 if term is None else term}</td>
    <td>Signing Date: 2025-07-01</td><td>Expiration Status: UFA</td>
    <td>Signing Team: <a href="/team/{signing_team}">Fixture Team</a></td></tr></table>
    <table><tr><td>Season</td><td>Cap Hit</td><td>NHL Salary</td><td>Signing Bonus</td><td>Perf. Bonuses</td><td>Clause</td></tr>{rows}</table></div>'''


class SourceFixtures:
    def __init__(self):
        self.calls = []
        self.events = [transaction()]
        self.status = {}
        self.contracts = {player: contract_page(player) for player in (1001, 1002, 1003)}
        self.mutate = lambda path, data: data

    def transport(self, url, **kwargs):
        self.calls.append(url)
        parsed = urlparse(url)
        if self.status.get(parsed.path):
            return Response(self.status[parsed.path], b"source unavailable")
        if parsed.netloc == "cap-space.com":
            body = self.contracts[int(parsed.path.split(":")[-1])]
        elif parsed.netloc == "capwages.com":
            body = self.capwages
        elif parsed.netloc == "sportsdata.usatoday.com":
            body = page(self.events)
        elif parsed.path == "/v1/standings/now":
            data = {"standings": [{"seasonId": season_id(2026), "gameTypeId": 2,
                    "teamAbbrev": {"default": abbr}, "teamName": {"default": name}}
                    for name, abbr in (("Toronto Maple Leafs", "TOR"), ("Calgary Flames", "CGY"))]}
            body = json.dumps(self.mutate(parsed.path, data))
        elif parsed.path.startswith("/v1/player/"):
            player = int(parsed.path.split("/")[3])
            data = {"playerId": player, "isActive": player != 1003,
                    "firstName": {"default": "Test"}, "lastName": {"default": f"Player {player}"},
                    "position": "L", "birthDate": "1995-01-01", "birthCountry": "CAN", "shootsCatches": "L"}
            body = json.dumps(self.mutate(parsed.path, data))
        elif parsed.path.startswith("/v1/roster/"):
            pieces = parsed.path.split("/")
            year = 2026 if pieces[-1] == "current" else int(pieces[-1]) // 10000
            players = [1001 if pieces[-2] == "TOR" else (1003 if year == 2025 else 1002)]
            data = {"forwards": [{"id": player} for player in players], "defensemen": [], "goalies": []}
            body = json.dumps(self.mutate(parsed.path, data))
        elif parsed.path.startswith("/v1/gamecenter/"):
            game_id = int(parsed.path.split("/")[3])
            data = {"id": game_id, "playerByGameStats": {side: {"forwards": [{"playerId": player}], "defense": [], "goalies": []}
                    for side, player in (("homeTeam", 1004), ("awayTeam", 1001))}}
            body = json.dumps(self.mutate(parsed.path, data))
        else:
            path = parsed.path.removeprefix("/stats/rest/en/")
            params = parse_qs(parsed.query)
            exp = params.get("cayenneExp", [""])[0]
            year = int(re.search(r"seasonId=(\d+)", exp)[1]) // 10000 if exp else None
            game_type = int(re.search(r"gameTypeId=(\d+)", exp)[1]) if exp else None
            team = re.search(r"teamId=(\d+)", exp)
            if path == "team":
                rows = [{"id": team_id, "franchiseId": team_id, "leagueId": 133, "fullName": name, "triCode": abbr}
                        for team_id, name, abbr in ((10, "Toronto Maple Leafs", "TOR"), (20, "Calgary Flames", "CGY"))]
            elif path == "franchise":
                rows = [{"id": value, "fullName": f"Franchise {value}"} for value in (10, 20)]
            elif path == "season":
                rows = [{"id": season_id(value)} for value in (2008, 2025, 2026, 2027)]
            elif path == "team/summary":
                rows = [{"teamId": value, "seasonId": season_id(year), "teamFullName": name}
                        for value, name in ((10, "Toronto Maple Leafs"), (20, "Calgary Flames"))] if game_type == 2 else []
            elif path == "skater/summary":
                players = [(1001, 10), (1003 if year == 2025 else 1002, 20)]
                rows = [{"playerId": player, "seasonId": season_id(year), "gamesPlayed": 10,
                         "goals": 2, "assists": 3, "points": 5, "shots": 20, "shootingPct": 0.1,
                         "timeOnIcePerGame": 912.33, "teamAbbrevs": "TOR" if team_id == 10 else "CGY"}
                        for player, team_id in players if (not team or int(team[1]) == team_id) and game_type == 2]
            elif path == "goalie/summary":
                rows = []
            else:
                raise AssertionError(f"Unexpected fixture URL {url}")
            start, limit = int(params.get("start", [0])[0]), int(params.get("limit", [100])[0])
            data = {"data": rows[start:start+limit], "total": len(rows)}
            body = json.dumps(self.mutate(parsed.path, data))
        return Response(200, body.encode())


def runner(fixtures=None, store=None, *, mappings=(), **options):
    fixtures = fixtures or SourceFixtures()
    store = store or ContractStore()
    store.now = NOW
    defaults = (MappingCandidate("usatoday", "player", "p1", 1001, "reviewed cross-ID fixture"),
                MappingCandidate("usatoday", "player", "p2", 1002, "reviewed cross-ID fixture"),
                MappingCandidate("usatoday", "team", "t10", 10, "reviewed cross-ID fixture"),
                MappingCandidate("usatoday", "team", "t20", 20, "reviewed cross-ID fixture"))
    client = SourceClient({source: RequestPolicy(minimum_interval_seconds=0, attempts=1) for source in ("nhl", "capspace", "capwages", "usatoday")}, transport=fixtures.transport)
    return Executor(store, core_operations(mappings=(*defaults, *mappings), **options),
                    target_environment="dev", client=client, now=lambda: NOW, pause=lambda _: None)


def create_runtime(environment):
    if environment != "dev":
        raise ValueError("Offline core source runtime supports dev only")
    return runner()

"""Offline public feed shapes; illustrative NHL/EDGE, recorded MoneyPuck headers."""
from copy import deepcopy
from io import BytesIO, StringIO
from urllib.parse import parse_qs, urlparse
from zipfile import ZipFile
import csv
import json
import re
from uuid import uuid4

from app.jobs.game_data_operations import game_data_operations
from app.jobs.shared.access_contracts import StoredRecord, make_write
from app.jobs.shared.data_contracts import PlayerProfile, SeasonRecord, Team, TeamSeason
from app.jobs.shared.execution import Executor
from app.jobs.shared.source_requests import RequestPolicy, Response, SourceClient
from app.jobs.sources.nhl import season_id
from .contract_store import ContractStore
from .execution_fixtures import NOW

P1, P2, P3 = 8478402, 8478403, 8478404
GAME = 2026020001


def csv_body(rows, fields=None):
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fields or tuple(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def archive(body, *, name="shots.csv"):
    output = BytesIO()
    with ZipFile(output, "w") as zipped:
        zipped.writestr(name, body)
    return output.getvalue()


def schedule_game(game_id=GAME, game_type=2, **changes):
    return {"id": game_id, "season": season_id(2026), "gameType": game_type,
            "gameState": "OFF", "startTimeUTC": "2026-10-11T18:00:00Z",
            "homeTeam": {"id": 10, "abbrev": "TOR", "score": 1},
            "awayTeam": {"id": 20, "abbrev": "CGY", "score": 0}, **changes}


def boxscore():
    game = schedule_game()
    groups = {}
    for side, player, goals in (("homeTeam", P1, 1), ("awayTeam", P2, 0)):
        groups[side] = {"forwards": [{"playerId": player, "goals": goals, "assists": 0, "sog": 2, "toi": "20:01"}],
                        "defense": [], "goalies": [{"playerId": P3, "saves": 2, "shotsAgainst": 2, "toi": "60:00"}]}
    return {**game, "playerByGameStats": groups, "gameOutcome": {"lastPeriodType": "REG"}}


def event(event_id=1, order=10, **changes):
    return {"eventId": event_id, "sortOrder": order, "typeDescKey": "goal",
            "periodDescriptor": {"number": 1, "periodType": "REG"}, "timeInPeriod": "01:00",
            "details": {"scoringPlayerId": P1, "eventOwnerTeamId": 10, "xCoord": 80, "yCoord": 5}, **changes}


def stats(kind):
    row = {"season": "2026", "team": "TOR", "situation": "all", "icetime": "1200.0"}
    if kind in ("skaters", "goalies"):
        row["playerId"] = str(P1 if kind == "skaters" else P3)
    if kind == "skaters":
        row.update(I_F_xGoals="1.25", OnIce_F_xGoals="2.5", onIce_xGoalsPercentage="0.55", I_F_goals="1.0",
                   I_F_primaryAssists="1.0", I_F_secondaryAssists="0.0", I_F_points="2.0", I_F_shotsOnGoal="3.0")
    elif kind == "goalies":
        row.update(xGoals="2.25", goals="2.0")
    else:
        row.update(xGoalsFor="3.25", xGoalsAgainst="2.25")
        if kind == "lines":
            row["lineId"] = f"{P1}{P2}{P3}"
        else:
            row["iceTime"] = row.pop("icetime")
    return row


def shot(shot_id=1, **changes):
    return {"shotID": str(shot_id), "game_id": "20001", "season": "2026", "event": "GOAL", "goal": "1",
            "team": "TOR", "shooterPlayerId": str(P1), "xCord": "80", "yCord": "5",
            "arenaAdjustedXCord": "79.5", "arenaAdjustedYCord": "5.5", "xGoal": "0.12", **changes}


def edge_detail(entity="player", identity=P1, game_type=2):
    return {("playerId" if entity == "player" else "teamId"): identity, "season": season_id(2026), "gameType": game_type,
            "seasonsWithEdgeStats": [{"season": season_id(2026), "gameTypes": [2, 3]}],
            "skatingSpeed": {"speedMax": {"imperial": 22.1, "metric": 35.56}, "burstsOver22": 2},
            "skatingDistance": {"distanceTotal": {"imperial": 12.4, "metric": 19.96}},
            "shotLocation": {"highDanger": {"shotsOnGoal": 5, "goals": 1}},
            "zoneTime": {"offensiveZonePctg": 0.41}}


class Fixtures:
    def __init__(self):
        self.calls, self.status = [], {}
        self.games = [schedule_game(), schedule_game(2026010001, 1), schedule_game(2026030001, 3, gameState="FUT")]
        self.box = boxscore()
        self.play = {**schedule_game(), "plays": [event()]}
        self.stat_rows = {kind: [stats(kind)] for kind in ("skaters", "goalies", "teams", "lines")}
        self.shots = [shot()]
        self.edge = lambda entity, identity, kind: edge_detail(entity, identity, kind)
        self.mutate = lambda path, data: data
        self.csv_override, self.zip_override = {}, None

    def transport(self, url, **kwargs):
        self.calls.append(url)
        parsed = urlparse(url)
        path = parsed.path
        if path in self.status:
            return Response(self.status[path], b"unavailable")
        if path.startswith("/v1/club-schedule-season/"):
            data = {"season": season_id(2026), "games": deepcopy(self.games)}
        elif path.endswith("/boxscore"):
            data = deepcopy(self.box)
        elif path.endswith("/play-by-play"):
            data = deepcopy(self.play)
        elif path.startswith("/v1/player/"):
            identity = int(path.split("/")[3])
            data = {"playerId": identity, "firstName": {"default": "Historical"}, "lastName": {"default": "Player"},
                    "isActive": False, "position": "C"}
        elif path.startswith("/v1/roster/"):
            data = {"forwards": [{"id": P1}, {"id": P2}], "defensemen": [], "goalies": [{"id": P3}]}
        elif path.startswith("/stats/rest/en/"):
            kind = path.split("/")[4]
            expression = parse_qs(parsed.query)["cayenneExp"][0]
            game_type = int(re.search(r"gameTypeId=(\d+)", expression)[1])
            rows = ([{"teamId": 10}, {"teamId": 20}] if kind == "team" else
                    [{"playerId": P1}, {"playerId": P2}] if kind == "skater" else [{"playerId": P3}]) if game_type == 2 else []
            for row in rows:
                row["seasonId"] = season_id(2026)
            params = parse_qs(parsed.query)
            start, limit = int(params["start"][0]), int(params["limit"][0])
            data = {"data": rows[start:start+limit], "total": len(rows)}
        elif path.startswith("/v1/edge/"):
            endpoint, identity, _, game_type = path.split("/")[-4:]
            data = self.edge("team" if endpoint == "team-detail" else "player", int(identity), int(game_type))
        elif parsed.netloc == "moneypuck.com":
            kind = path.split("/")[-1].removesuffix(".csv")
            body = self.csv_override.get(kind) or csv_body(self.stat_rows[kind], fields=tuple(stats(kind)))
            return Response(200, body)
        elif parsed.netloc == "peter-tanner.com":
            return Response(200, self.zip_override if self.zip_override is not None else archive(csv_body(self.shots, fields=tuple(shot()))))
        else:
            raise AssertionError(f"Unexpected fixture URL: {url}")
        return Response(200, json.dumps(self.mutate(path, data)).encode())


def seed(executor, dataset, record):
    write = make_write(dataset, record, expected_revision=None)
    executor.store.rows["dev", dataset, write.key] = [StoredRecord(write=write, revision=1, accepted_at=NOW, run_id=uuid4())]


def runner(fixtures=None, *, seed_references=True, **policies):
    fixtures = fixtures or Fixtures()
    store = ContractStore()
    store.now = NOW
    client = SourceClient({source: RequestPolicy(attempts=1, minimum_interval_seconds=0) for source in ("nhl", "moneypuck")}, transport=fixtures.transport)
    executor = Executor(store, game_data_operations(**policies), target_environment="dev", client=client, now=lambda: NOW, pause=lambda _: None)
    if seed_references:
        seed(executor, "seasons", SeasonRecord(season=2026, end_year=2027, label="2026-27"))
        for identity, abbreviation in ((10, "TOR"), (20, "CGY")):
            seed(executor, "teams", Team(team_id=identity, nhl_team_id=identity, abbreviation=abbreviation, name=abbreviation, active=True))
            seed(executor, "team_seasons", TeamSeason(team_id=identity, season=2026, name=abbreviation, abbreviation=abbreviation))
        for identity in (P1, P2, P3):
            seed(executor, "player_profiles", PlayerProfile(player_id=identity, nhl_player_id=identity, first_name="Fixture", last_name="Player", active=False))
    return executor


def create_runtime(environment):
    if environment != "dev":
        raise ValueError("Offline game-data runtime supports dev only")
    return runner()

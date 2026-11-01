"""Saved source responses for database ingestion scenarios."""

import json
from dataclasses import dataclass, field
import requests
from contextlib import nullcontext


@dataclass(slots=True, kw_only=True, frozen=True)
class CsvResponse:
    text: str
    status_code: int = 200

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return json.loads(self.text)


def build_json_response(payload: object) -> CsvResponse:
    return CsvResponse(text=json.dumps(payload))


def build_capwages_response(payload: object) -> CsvResponse:
    return CsvResponse(
        text='<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script>"
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class MoneyPuckSession:
    skater_games: int = 12
    season: int = 2025

    def get(self, url, timeout, params=None):
        if "skaters.csv" in url:
            header = (
                "playerId,season,name,team,position,situation,games_played,"
                "icetime,shifts,gameScore,I_F_points,I_F_goals\n"
            )
            old = f"1001,{self.season},Fixture Skater,AAA,C,all,11,1300,160,4.5,9,4\n"
            new = (
                f"1001,{self.season},Fixture Skater,AAA,C,all,"
                f"{self.skater_games},1400,170,5.5,10,5\n"
            )
            return CsvResponse(text=header + old + new)
        return CsvResponse(
            text="playerId,season,name,team,position,situation,games_played,"
            "icetime,xGoals,goals,ongoal\n"
            f"2001,{self.season},Fixture Goalie,BBB,G,all,9,1000,15.5,14,240\n"
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class CapWagesSession:
    cap_hit: str = "$1,000,000"
    fail_profile: bool = False
    player_name: str = "Contract Fixture"

    def get(self, url, timeout, params=None):
        if url.endswith("/players/active"):
            row = [self.player_name, "contract-fixture", "AAA", "C"] + [None] * 27
            row[7] = "USA"
            row[30] = "98-2-3"
            payload = {"props": {"pageProps": {"playersArray": [row]}}}
            return build_capwages_response(payload)
        if self.fail_profile:
            raise requests.ConnectionError("fixture profile failed")
        payload = {
            "props": {
                "pageProps": {
                    "player": {
                        "contracts": [
                            {
                                "signingTeam": "AAA",
                                "value": "$2,000,000",
                                "expiryStatus": "UFA",
                                "type": "STANDARD",
                                "details": [
                                    {"season": "2025-26", "capHit": self.cap_hit}
                                ],
                            }
                        ]
                    }
                }
            }
        }
        return build_capwages_response(payload)


@dataclass(slots=True, kw_only=True, frozen=True)
class ScheduleSession:
    game_ids: tuple[int, ...] = (2025020001, 2025020002)

    def get(self, url, timeout, params=None):
        games = [
            {
                "id": game_id,
                "gameType": 2,
                "awayTeam": {"abbrev": "AAA", "score": 2},
                "homeTeam": {"abbrev": "BBB", "score": 3},
                "venue": {"default": "Fixture Arena"},
                "gameState": "FINAL",
                "startTimeUTC": "2025-10-01T23:00:00Z",
            }
            for game_id in self.game_ids
        ]
        return build_json_response(
            {
                "gameWeek": [{"date": "2025-10-01", "games": games}],
                "nextStartDate": None,
            }
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class NhlRosterSession:
    abbreviation: str = "AAA"

    def get(self, url, timeout, params=None):
        if url.endswith("/standings/now"):
            return build_json_response(
                {
                    "standings": [
                        {
                            "teamAbbrev": {"default": self.abbreviation},
                            "teamName": {"default": "Alphas"},
                            "placeName": {"default": "Alpha City"},
                        }
                    ]
                }
            )
        return build_json_response(
            {
                "forwards": [
                    {
                        "id": 3001,
                        "firstName": {"default": "Roster"},
                        "lastName": {"default": "Fixture"},
                        "birthDate": "2000-01-01",
                        "positionCode": "C",
                        "shootsCatches": "L",
                        "birthCountry": "CAN",
                    }
                ],
                "defensemen": [],
                "goalies": [],
            }
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class SavedJsonSession:
    payload: object

    def get(self, url, timeout, params=None):
        return build_json_response(self.payload)


@dataclass(slots=True, kw_only=True, frozen=True)
class InvalidContractSession:
    mode: str
    session: CapWagesSession = CapWagesSession()

    def get(self, url, timeout, params=None):
        response = self.session.get(url, timeout)
        if url.endswith("/players/active"):
            return response
        payload = json.loads(response.text.split(">", 1)[1].rsplit("<", 1)[0])
        details = payload["props"]["pageProps"]["player"]["contracts"][0]["details"]
        if self.mode == "gap":
            details.append({"season": "2027-28", "capHit": "$1,000,000"})
        if self.mode == "cap":
            details[0]["capHit"] = "$100,000,000"
        return build_capwages_response(payload)


@dataclass(slots=True, kw_only=True, frozen=True)
class SessionLifecycle:
    closures: list[bool] = field(default_factory=list)
    failure: BaseException | None = None

    def close(self) -> None:
        self.closures.append(True)
        if self.failure is not None:
            raise self.failure


def build_nhl_stat_rows(kind, season, game_type, *, goals=5):
    if kind == "skater":
        row = {
            "playerId": 1001,
            "skaterFullName": "Fixture Skater",
            "teamAbbrevs": "AAA,BBB",
            "positionCode": "C",
            "gamesPlayed": 10,
            "goals": goals,
            "assists": 7,
            "points": goals + 7,
            "shots": 40,
        }
        return [row, dict(row)]
    row = {
        "playerId": 2001,
        "goalieFullName": "Fixture Goalie",
        "teamAbbrevs": "BBB",
        "gamesPlayed": 8,
        "wins": 5,
        "losses": 2,
        "otLosses": 1,
        "shotsAgainst": 220,
        "saves": 207,
        "goalsAgainst": 13,
    }
    return [row, dict(row)]


@dataclass(slots=True, kw_only=True, frozen=True)
class FixtureStatsClient:
    goals: int
    csv_text: str = ""

    def get_json(self, url, *, timeout=30, params=None):
        kind = "skater" if "/skater/" in url else "goalie"
        assert params is not None
        season = int(params["cayenneExp"].split("=", 1)[1][:4])
        game_type = int(params["cayenneExp"][-1])
        return {"data": build_nhl_stat_rows(kind, season, game_type, goals=self.goals)}

    def get_csv(self, url, *, timeout=60):
        return self.csv_text


@dataclass(slots=True, kw_only=True, frozen=True)
class FixtureStatsFactory:
    goals: int

    def __call__(self):
        return nullcontext(FixtureStatsClient(goals=self.goals))

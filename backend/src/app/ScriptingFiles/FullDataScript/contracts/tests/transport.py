"""Scripted profile transport that rejects unexpected requests."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from app.ScriptingFiles.FullDataScript.contracts.tests.fixtures import SavedResponse
import json
from app.ScriptingFiles.FullDataScript import capspace


@dataclass(slots=True, kw_only=True, frozen=True)
class ScriptedProfileSession:
    responses: tuple[SavedResponse | Exception, ...] = ()
    routes: Mapping[str, SavedResponse] = field(default_factory=dict)
    calls: list[tuple[str, float]] = field(default_factory=list)

    def get(self, url: str, *, timeout: float) -> SavedResponse:
        index = len(self.calls)
        self.calls.append((url, timeout))
        response = self.routes[url] if len(self.routes) > 0 else self.responses[index]
        if isinstance(response, Exception):
            raise response
        return response


@dataclass(slots=True, kw_only=True, frozen=True)
class SleepRecorder:
    delays: list[float] = field(default_factory=list)

    def __call__(self, delay: float) -> None:
        self.delays.append(delay)


@dataclass(slots=True, kw_only=True, frozen=True)
class ProfileScenario:
    session: ScriptedProfileSession
    sleep: SleepRecorder


@dataclass(slots=True, kw_only=True, frozen=True)
class CandidateCursor:
    rows: tuple[tuple[object, ...], ...] = ()
    statements: list[tuple[str, Sequence[object] | None]] = field(default_factory=list)

    def execute(self, statement: str, params: Sequence[object] | None = None) -> None:
        self.statements.append((statement, params))

    def fetchall(self) -> tuple[tuple[object, ...], ...]:
        return self.rows


def capwages_html(nhl_id: int | None, season: int = 2010) -> str:
    player = {
        "contracts": [
            {
                "id": "capwages-contract",
                "type": "Standard Contract",
                "value": "$1,000,000",
                "term": 1,
                "signingDate": "2010-07-01",
                "details": [
                    {
                        "season": f"{season}-{str(season + 1)[-2:]}",
                        "capHit": "$1,000,000",
                    }
                ],
            }
        ],
    }
    if nhl_id is not None:
        player["nhlId"] = nhl_id
    payload = {"props": {"pageProps": {"player": player}}}
    return (
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script>"
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class IdentityScenario:
    candidate: capspace.Candidate
    html: str


@dataclass(slots=True, kw_only=True, frozen=True)
class RequestScenario:
    candidate: capspace.Candidate
    session: ScriptedProfileSession


@dataclass(slots=True, kw_only=True, frozen=True)
class TeamResolutionScenario:
    teams: dict[str, int]
    stints: dict[int, tuple[int, ...]]


@dataclass(slots=True, kw_only=True, frozen=True)
class MetricsScenario:
    covered: capspace.Candidate
    missing_id: capspace.Candidate
    success: capspace.ProfileResult
    failure: capspace.ProfileResult

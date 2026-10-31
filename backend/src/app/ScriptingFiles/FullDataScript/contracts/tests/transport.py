"""Scripted profile transport that rejects unexpected requests."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.ScriptingFiles.FullDataScript.contracts.tests.fixtures import SavedResponse


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

"""Behavioral roster collaborators with in-memory persistence."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

from app.ScriptingFiles.FullDataScript.roster_status.domain import (
    FetchResult,
    RosterStatus,
    StoredPlayer,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class MemoryRosterRepository:
    players: tuple[StoredPlayer, ...] = ()
    ltir_player_ids: frozenset[int] = frozenset()
    updates: dict[int, RosterStatus] = field(default_factory=dict)
    ahl_mappings: list[tuple[int, str, str]] = field(default_factory=list)

    def load_players(self) -> tuple[StoredPlayer, ...]:
        return self.players

    def load_active_ltir_player_ids(self, as_of: date) -> frozenset[int]:
        return self.ltir_player_ids

    def bulk_update_statuses(self, updates: Mapping[int, RosterStatus]) -> None:
        self.updates.update(updates)

    def save_ahl_external_ids(self, matches: Iterable[tuple[int, str, str]]) -> None:
        self.ahl_mappings.extend(matches)

    def __len__(self) -> int:
        return len(self.players)


@dataclass(slots=True, kw_only=True, frozen=True)
class FixedRosterFeed:
    result: FetchResult = field(default_factory=FetchResult)

    def fetch_current_rosters(self) -> FetchResult:
        return self.result

    def __len__(self) -> int:
        return len(self.result.items)


@dataclass(slots=True, kw_only=True, frozen=True)
class MemoryHttpClient:
    responses: Mapping[str, object]
    calls: list[tuple[str, Mapping[str, str] | None]] = field(default_factory=list)

    def get_json(self, url: str, params: Mapping[str, str] | None = None) -> object:
        self.calls.append((url, params))
        key = url if params is None else params.get("team_id", params["view"])
        response = self.responses[key]
        if isinstance(response, Exception):
            raise response
        return response

    def __len__(self) -> int:
        return len(self.calls)

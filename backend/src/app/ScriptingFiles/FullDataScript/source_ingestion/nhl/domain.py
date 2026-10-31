"""NHL source options and immutable snapshots."""

from dataclasses import dataclass
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    PlayerKind,
    RosterPlayer,
    StatRow,
    Team,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class NhlStatsOptions:
    first_season: int = 2008
    last_season: int = 2025
    workers: int = 6
    page_size: int = 100
    maximum_pages: int = 1000


@dataclass(slots=True, kw_only=True, frozen=True)
class StatsJob:
    kind: PlayerKind
    season: int
    game_type: int


@dataclass(slots=True, kw_only=True, frozen=True)
class NhlStatsSnapshot:
    rows: tuple[StatRow, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class NhlRosterOptions:
    season: int
    minimum_teams: int = 30
    minimum_active_players: int = 500


@dataclass(slots=True, kw_only=True, frozen=True)
class NhlRosterSnapshot:
    season: int
    teams: tuple[Team, ...]
    players: tuple[RosterPlayer, ...]

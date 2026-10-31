"""Schedule fetch options and immutable game snapshots."""

from dataclasses import dataclass
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import Game


@dataclass(slots=True, kw_only=True, frozen=True)
class ScheduleOptions:
    season: int = 2026
    minimum_games: int = 100


@dataclass(slots=True, kw_only=True, frozen=True)
class ScheduleSnapshot:
    season: int
    games: tuple[Game, ...]
    records_read: int

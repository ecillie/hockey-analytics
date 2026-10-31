"""MoneyPuck inputs and immutable validated snapshots."""

from dataclasses import dataclass
from pathlib import Path
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    DataQualityReport,
    PlayerKind,
    StatRow,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class MoneyPuckOptions:
    skater_file: Path
    goalie_file: Path
    expected_seasons: tuple[int, ...] = tuple(range(2008, 2026))
    minimum_rows_per_kind: int = 100
    maximum_duplicate_ratio: float = 0.01
    skater_url: str = "https://moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/skaters.csv"
    goalie_url: str = "https://moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/goalies.csv"

    def historical_file(self, kind: PlayerKind) -> Path:
        return self.skater_file if kind == PlayerKind.SKATER else self.goalie_file

    def current_url(self, kind: PlayerKind) -> str:
        return self.skater_url if kind == PlayerKind.SKATER else self.goalie_url


@dataclass(slots=True, kw_only=True, frozen=True)
class MoneyPuckSnapshot:
    rows: tuple[StatRow, ...]
    quality: tuple[DataQualityReport, ...]

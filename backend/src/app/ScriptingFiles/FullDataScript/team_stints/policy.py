"""Ordered optional season bounds for team-stint reconstruction."""

from dataclasses import dataclass
from app.ScriptingFiles.FullDataScript.team_stints.errors import SeasonRangeError


@dataclass(slots=True, kw_only=True, frozen=True)
class SeasonRangePolicy:
    first_season: int | None
    last_season: int | None

    def find_violation(self) -> SeasonRangeError | None:
        if (
            self.first_season is not None
            and self.last_season is not None
            and self.first_season > self.last_season
        ):
            return SeasonRangeError(
                first_season=self.first_season, last_season=self.last_season
            )
        return None

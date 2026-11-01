"""Typed invalid season range for team-stint queries."""


class SeasonRangeError(ValueError):
    def __init__(self, *, first_season: int, last_season: int) -> None:
        super().__init__("first_season cannot be greater than last_season")
        self.first_season = first_season
        self.last_season = last_season

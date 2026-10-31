"""Validation of NHL and HockeyTech response shapes."""

from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field


type PositiveFeedId = Annotated[int, Field(gt=0, strict=True)]
type TextFeedId = Annotated[str, Field(min_length=1, strict=True, pattern=r"\S")]
type FeedId = PositiveFeedId | TextFeedId


class FeedModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class LocalizedName(FeedModel):
    default: str = ""


class LocalizedTeam(FeedModel):
    default: TextFeedId


class NhlStanding(FeedModel):
    teamAbbrev: LocalizedTeam


class NhlStandings(FeedModel):
    standings: tuple[NhlStanding, ...]


class NhlPlayer(FeedModel):
    id: FeedId
    firstName: LocalizedName = Field(default_factory=LocalizedName)
    lastName: LocalizedName = Field(default_factory=LocalizedName)


class NhlRoster(FeedModel):
    forwards: tuple[NhlPlayer, ...]
    defensemen: tuple[NhlPlayer, ...]
    goalies: tuple[NhlPlayer, ...]


class AhlTeam(FeedModel):
    id: int | str = ""


class AhlBootstrap(FeedModel):
    current_season_id: FeedId | None = None
    current_league_id: FeedId = "4"
    teamsNoAll: tuple[AhlTeam, ...]


class AhlPlayer(FeedModel):
    player_id: FeedId
    name: TextFeedId
    birthdate: str | None = None


class AhlEntry(FeedModel):
    row: AhlPlayer


class AhlSection(FeedModel):
    data: tuple[AhlEntry, ...]


class AhlGroup(FeedModel):
    sections: tuple[AhlSection, ...]


class AhlRoster(FeedModel):
    roster: tuple[AhlGroup, ...]

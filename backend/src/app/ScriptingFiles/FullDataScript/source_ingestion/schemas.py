"""Validation schemas at JSON, CSV, and normalized identity boundaries."""

import json
from datetime import date
from typing import Annotated
from pydantic import (
    BaseModel,
    BeforeValidator,
    AfterValidator,
    ConfigDict,
    JsonValue,
    PlainSerializer,
    TypeAdapter,
    Field,
    ValidationError,
)

from app.ScriptingFiles.FullDataScript.source_ingestion.errors import (
    IntegerValueViolation,
    PayloadViolation,
    TeamAbbreviationViolation,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.util import (
    parse_strict_integer,
    parse_team_abbreviation,
)


def parse_required_integer(value: object) -> int:
    result = parse_strict_integer(value)
    if result is None:
        raise IntegerValueViolation(value=value)
    return result


def normalize_team_abbreviation(value: str) -> str:
    abbreviation = parse_team_abbreviation(value)
    if abbreviation is None:
        raise TeamAbbreviationViolation(value=value)
    return abbreviation


def extract_localized_value(value: object) -> object:
    if isinstance(value, dict):
        default = value.get("default")
        return (
            next(iter(value.values()), None)
            if default is None or default == ""
            else default
        )
    return value


type TeamAbbreviation = Annotated[str, AfterValidator(normalize_team_abbreviation)]


type Integer = Annotated[int, BeforeValidator(parse_required_integer)]
type NonnegativeInteger = Annotated[Integer, Field(ge=0)]
type Season = Annotated[Integer, Field(ge=1900, le=2200)]
type NonnegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
type NonemptyText = Annotated[str, Field(min_length=1, pattern=r"\S")]
type PageTotal = Annotated[int, Field(ge=0, strict=True)]


class BoundaryModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class MoneyPuckRow(BoundaryModel):
    playerId: Integer
    season: Season
    name: NonemptyText
    situation: NonemptyText
    games_played: NonnegativeInteger
    icetime: NonnegativeFloat
    team: str | None = None
    position: str | None = None


class NhlStatRow(BoundaryModel):
    playerId: Integer
    teamAbbrevs: str | None = None
    skaterFullName: str | None = None
    goalieFullName: str | None = None
    lastName: str | None = None
    positionCode: str | None = None
    shootsCatches: str | None = None
    gamesPlayed: NonnegativeInteger


class SkaterStatRow(NhlStatRow):
    goals: NonnegativeInteger
    assists: NonnegativeInteger
    points: NonnegativeInteger


class GoalieStatRow(NhlStatRow):
    shotsAgainst: NonnegativeInteger
    saves: NonnegativeInteger
    goalsAgainst: NonnegativeInteger


type PageRows = tuple[dict[str, object], ...]
type JsonPageRows = tuple[dict[str, JsonValue], ...]


def serialize_page_rows(value: object) -> tuple[str, ...]:
    rows = TypeAdapter(JsonPageRows).validate_python(value)
    return tuple(json.dumps(row) for row in rows)


def decode_page_rows(value: tuple[str, ...]) -> PageRows:
    return tuple(json.loads(row) for row in value)


type PageSnapshots = Annotated[
    tuple[str, ...],
    BeforeValidator(serialize_page_rows),
    PlainSerializer(decode_page_rows, return_type=PageRows),
]


class StatsPage(BoundaryModel):
    model_config = ConfigDict(serialize_by_alias=True)

    data_snapshot: PageSnapshots = Field(
        validation_alias="data", serialization_alias="data"
    )
    total: PageTotal | None = None

    @property
    def data(self) -> PageRows:
        return decode_page_rows(self.data_snapshot)


type LocalizedText = Annotated[str | None, BeforeValidator(extract_localized_value)]
type LocalizedTeam = Annotated[
    TeamAbbreviation, BeforeValidator(extract_localized_value)
]


class Standing(BoundaryModel):
    teamAbbrev: LocalizedTeam
    teamName: LocalizedText = None
    placeName: LocalizedText = None


class Standings(BoundaryModel):
    standings: tuple[Standing, ...]


class RosterPlayer(BoundaryModel):
    id: Integer
    firstName: LocalizedText = None
    lastName: LocalizedText = None
    birthDate: date | None = None
    positionCode: str | None = None
    shootsCatches: str | None = None
    birthCountry: str | None = None


class Roster(BoundaryModel):
    forwards: tuple[RosterPlayer, ...]
    defensemen: tuple[RosterPlayer, ...]
    goalies: tuple[RosterPlayer, ...]


class GameTeam(BoundaryModel):
    abbrev: TeamAbbreviation
    score: Integer | None = None


class ScheduleGame(BoundaryModel):
    id: Integer
    gameType: Integer
    awayTeam: GameTeam
    homeTeam: GameTeam
    startTimeUTC: str | None = None
    venue: LocalizedText = None
    gameState: str | None = None


class ScheduleDay(BoundaryModel):
    model_config = ConfigDict(serialize_by_alias=True)

    date: date
    games_snapshot: PageSnapshots = Field(
        validation_alias="games", serialization_alias="games"
    )

    @property
    def games(self) -> PageRows:
        return decode_page_rows(self.games_snapshot)


class SchedulePage(BoundaryModel):
    gameWeek: tuple[ScheduleDay, ...]
    nextStartDate: date | None = None


def validate_payload[T: BaseModel](value: object, schema: type[T], *, source: str) -> T:
    try:
        return schema.model_validate(value)
    except ValidationError as exc:
        issues = tuple(
            f"{'.'.join(map(str, issue['loc']))}: {issue['msg']}"
            for issue in exc.errors(include_input=False, include_url=False)
        )
        raise PayloadViolation(
            source=source,
            reason=f"source response does not match {schema.__name__}: {'; '.join(issues)}",
        ) from exc

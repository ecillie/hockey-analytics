"""Logical record contracts for the data rebuild; no database engine is selected.

Validate normalized records, then retain source observations and revisions through
the access interfaces. Source parsing, source precedence, and orchestration are
separate responsibilities. These models do not alter the public API schemas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math
from types import MappingProxyType
from typing import Annotated, Any, Callable, Literal, Mapping
from uuid import UUID

from pydantic import (
    AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictInt,
    StrictStr, field_validator, model_validator,
)


CONTRACT_VERSION = "1"
Id = Annotated[StrictInt, Field(gt=0)]
Count = Annotated[StrictInt, Field(ge=0)]
Text = Annotated[StrictStr, Field(min_length=1)]
Season = Annotated[StrictInt, Field(ge=2008)]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Quantity = Annotated[Number, Field(ge=0)]
Money = Annotated[Count, Field(json_schema_extra={"unit": "USD cents"})]
Seconds = Annotated[Quantity, Field(json_schema_extra={"unit": "seconds"})]
Ratio = Annotated[Number, Field(ge=0, le=1, json_schema_extra={"unit": "ratio"})]
GameType = Literal[2, 3]
Position = Literal["C", "LW", "RW", "D", "G", "F"]
RosterStatus = Literal["ACTIVE", "MINORS", "LTIR", "UNKNOWN"]
EntityType = Literal["player", "team", "franchise", "game", "contract"]
Environment = Literal["dev", "nonprod", "prod"]
Mode = Literal["initial", "refresh", "backfill", "validation"]
Digest = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]


def canonical_json(value: Any) -> bytes:
    """Stable UTF-8 JSON representation; non-finite values are rejected."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _check_json(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite values cannot be accepted")
    if isinstance(value, Mapping):
        for child in value.values():
            _check_json(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _check_json(child)


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)

    @field_validator("game_type", mode="before", check_fields=False)
    @classmethod
    def integer_game_type(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("Game type must be an integer")
        return value

    @field_validator("*", mode="after")
    @classmethod
    def normalized_values(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            raise ValueError("Blank strings are missing values")
        if isinstance(value, datetime):
            if value.utcoffset() is None:
                raise ValueError("Timestamps require a timezone")
            return value.astimezone(timezone.utc)
        _check_json(value)
        return value

    @model_validator(mode="after")
    def consistency(self) -> Record:
        fields = type(self).model_fields
        if "team_scope" in fields:
            total = self.team_scope == "TOTAL"
            if total != (self.team_id is None):
                raise ValueError("TOTAL has no team; TEAM requires a team identity")
        if "goals" in fields and "assists" in fields and "points" in fields:
            if None not in (self.goals, self.assists, self.points):
                if self.points != self.goals + self.assists:
                    raise ValueError("Points must equal goals plus assists")
        if "saves" in fields and "shots_against" in fields:
            if self.saves is not None and self.shots_against is not None:
                if self.saves > self.shots_against:
                    raise ValueError("Saves exceed shots against")
        for start, end in (("effective_from", "effective_to"), ("started_at", "finished_at")):
            if start in fields and end in fields:
                lower, upper = getattr(self, start), getattr(self, end)
                if lower is not None and upper is not None and upper < lower:
                    raise ValueError(f"{end} precedes {start}")
        return self


class Franchise(Record):
    franchise_id: Id
    name: Text


class Team(Record):
    team_id: Id
    name: Text
    abbreviation: Text
    active: StrictBool
    nhl_team_id: Id | None = None
    city: Text | None = None
    franchise_id: Id | None = None


class SeasonRecord(Record):
    season: Season
    end_year: Season
    label: Text
    salary_cap: Money | None = None

    @model_validator(mode="after")
    def years(self) -> SeasonRecord:
        if self.end_year != self.season + 1:
            raise ValueError("A season ends in the next calendar year")
        return self


class TeamSeason(Record):
    team_id: Id
    season: Season
    name: Text
    abbreviation: Text
    franchise_id: Id | None = None


class PlayerProfile(Record):
    player_id: Id
    first_name: Text
    last_name: Text
    active: StrictBool
    nhl_player_id: Id | None = None
    birth_date: date | None = None
    position: Position | None = None
    nationality: Text | None = None
    shoots_catches: Literal["L", "R"] | None = None


class Membership(Record):
    membership_id: Id
    player_id: Id
    team_id: Id
    season: Season
    effective_from: date | None = None
    effective_to: date | None = None


class SourceMapping(Record):
    source: Text
    source_id: Text
    entity_type: EntityType
    canonical_id: Id


class Contract(Record):
    contract_id: Id
    player_id: Id
    start_season: Season
    end_season: Season
    term_years: Id
    is_entry_level: StrictBool
    signed_on: date | None = None
    signing_team_id: Id | None = None
    contract_type: Text | None = None
    expiry_status: Literal["RFA", "UFA"] | None = None
    total_value: Money | None = None
    average_value: Money | None = None
    clauses: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def term(self) -> Contract:
        if self.end_season < self.start_season:
            raise ValueError("Contract seasons are reversed")
        if self.term_years != self.end_season - self.start_season + 1:
            raise ValueError("Contract term does not match its covered seasons")
        return self


class ContractSeason(Record):
    contract_id: Id
    player_id: Id
    season: Season
    cap_hit: Money
    is_slide: StrictBool
    base_salary: Money | None = None
    signing_bonus: Money | None = None
    performance_bonus: Money | None = None
    total_cash: Money | None = None
    owning_team_id: Id | None = None
    cap_percentage: Ratio | None = None


class PlayerSeason(Record):
    player_id: Id
    season: Season
    game_type: GameType
    team_scope: Literal["TOTAL", "TEAM"]
    source: Text
    team_id: Id | None = None


class BasicStats(PlayerSeason):
    stat_kind: Literal["skater", "goalie"]
    games_played: Count
    goals: Count | None = None
    assists: Count | None = None
    points: Count | None = None
    time_on_ice: Seconds | None = None
    plus_minus: StrictInt | None = None
    penalty_minutes: Count | None = None
    power_play_goals: Count | None = None
    power_play_points: Count | None = None
    short_handed_goals: Count | None = None
    shots: Count | None = None
    shooting_percentage: Ratio | None = None
    wins: Count | None = None
    losses: Count | None = None
    overtime_losses: Count | None = None
    saves: Count | None = None
    shots_against: Count | None = None
    goals_against: Count | None = None
    shutouts: Count | None = None
    save_percentage: Ratio | None = None
    goals_against_average: Quantity | None = None


class TransactionParticipant(Record):
    player_id: Id
    role: Text | None = None


class Transaction(Record):
    source_id: Text
    source: Text
    event_date: date
    event_type: Text
    participants: Annotated[tuple[TransactionParticipant, ...], Field(min_length=1)]
    description: Text | None = None
    from_team_id: Id | None = None
    to_team_id: Id | None = None

    @model_validator(mode="after")
    def participants_unique(self) -> Transaction:
        ids = [participant.player_id for participant in self.participants]
        if len(ids) != len(set(ids)):
            raise ValueError("A transaction participant may occur only once")
        return self


class RosterState(Record):
    player_id: Id
    status: RosterStatus
    evidence: Annotated[tuple[UUID, ...], Field(min_length=1)]
    team_id: Id | None = None
    effective_date: date | None = None
    override_id: UUID | None = None


class RosterObservation(Record):
    snapshot_id: UUID
    player_id: Id
    team_id: Id
    observed_at: AwareDatetime
    complete_scope: StrictBool
    source: Text


class RosterOverride(Record):
    override_id: UUID
    player_id: Id
    status: RosterStatus
    effective_from: date
    reason: Text
    actor: Text
    team_id: Id | None = None
    effective_to: date | None = None


class Game(Record):
    game_id: Id
    nhl_game_id: Id
    season: Season
    game_type: GameType
    home_team_id: Id
    away_team_id: Id
    start_time: AwareDatetime
    status: Literal["SCHEDULED", "LIVE", "FINAL", "POSTPONED", "CANCELLED", "UNKNOWN"]
    home_score: Count | None = None
    away_score: Count | None = None

    @model_validator(mode="after")
    def teams_differ(self) -> Game:
        if self.home_team_id == self.away_team_id:
            raise ValueError("A game requires two distinct teams")
        return self


class GameStats(Record):
    game_id: Id
    team_id: Id
    entity_id: Id
    entity_type: Literal["player", "team"]
    goals: Count | None = None
    assists: Count | None = None
    shots: Count | None = None
    time_on_ice: Seconds | None = None
    saves: Count | None = None
    shots_against: Count | None = None


class GameEvent(Record):
    game_id: Id
    event_id: Text
    source: Text
    event_type: Text
    period: Id
    time_in_period: Seconds
    order: Count
    player_id: Id | None = None
    team_id: Id | None = None
    x: Number | None = None
    y: Number | None = None
    coordinate_system: Text | None = None


class SkaterAdvanced(PlayerSeason):
    situation: Text
    ice_time: Seconds
    expected_goals: Quantity
    on_ice_expected_goals: Quantity | None = None
    on_ice_expected_goals_pct: Ratio | None = None
    game_score: Number | None = None
    shifts: Count | None = None
    individual_points: Count | None = None
    individual_goals: Count | None = None
    individual_primary_assists: Count | None = None
    individual_secondary_assists: Count | None = None
    individual_shots_on_goal: Count | None = None
    individual_unblocked_attempts: Count | None = None
    takeaways: Count | None = None
    giveaways: Count | None = None
    shots_blocked: Count | None = None
    penalties: Count | None = None
    penalties_drawn: Count | None = None
    offensive_zone_shift_starts: Count | None = None
    defensive_zone_shift_starts: Count | None = None
    neutral_zone_shift_starts: Count | None = None


class GoalieAdvanced(PlayerSeason):
    situation: Text
    ice_time: Seconds
    expected_goals_against: Quantity
    goals_against: Count | None = None


class TeamAdvanced(Record):
    team_id: Id
    season: Season
    game_type: GameType
    source: Text
    situation: Text
    ice_time: Seconds
    expected_goals_for: Quantity
    expected_goals_against: Quantity


class LineAdvanced(TeamAdvanced):
    player_ids: Annotated[tuple[Id, ...], Field(min_length=2, max_length=3)]

    @field_validator("player_ids")
    @classmethod
    def canonical_members(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Line members must be distinct")
        return tuple(sorted(value))


class Shot(Record):
    shot_id: Text
    game_id: Id
    season: Season
    game_type: GameType
    source: Text
    outcome: Literal["GOAL", "SAVE", "MISS"]
    player_id: Id | None = None
    team_id: Id | None = None
    x: Number | None = None
    y: Number | None = None
    coordinate_system: Text | None = None
    expected_goals: Ratio | None = None


class Measurement(Record):
    value: Number
    unit: Text
    definition: Text


class EdgeSeason(Record):
    entity_id: Id
    entity_type: Literal["player", "team"]
    season: Annotated[Season, Field(ge=2021)]
    game_type: GameType
    metrics: Annotated[dict[Text, Measurement], Field(min_length=1)]
    observed_at: AwareDatetime
    breakdowns: dict[Text, dict[Text, Measurement]] | None = None


class EdgeGame(EdgeSeason):
    game_id: Id


class EdgeEvent(EdgeSeason):
    event_id: Text
    game_id: Id | None = None


class InputRevision(Record):
    dataset: Text
    record_key: Annotated[tuple[JsonValue, ...], Field(min_length=1)]
    revision: Id
    content_digest: Digest


class DatasetVersion(Record):
    dataset_id: Text
    version: Text
    input_revisions: Annotated[tuple[InputRevision, ...], Field(min_length=1)]
    cutoff: AwareDatetime
    row_count: Count
    quality_results: Annotated[dict[Text, JsonValue], Field(min_length=1)]
    schema_version: Text
    transformation_version: Text
    feature_definitions: Annotated[dict[Text, JsonValue], Field(min_length=1)]
    scope: Annotated[dict[Text, JsonValue], Field(min_length=1)]
    content_digest: Digest
    point_in_time_supported: StrictBool


class SourceObservation(Record):
    observation_id: UUID
    source: Text
    source_key: Text
    dataset: Text
    observed_at: AwareDatetime
    content_digest: Digest
    transformation_version: Text
    scope: Annotated[dict[Text, JsonValue], Field(min_length=1)]
    payload: JsonValue
    source_updated_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def payload_digest(self) -> SourceObservation:
        if sha256(canonical_json(self.payload)).hexdigest() != self.content_digest:
            raise ValueError("Source payload digest differs")
        return self


class RunCounters(Record):
    read: Count = 0
    accepted: Count = 0
    rejected: Count = 0
    unresolved: Count = 0
    skipped: Count = 0

    @model_validator(mode="after")
    def accounted(self) -> RunCounters:
        if self.accepted + self.rejected + self.unresolved + self.skipped > self.read:
            raise ValueError("Accounted records exceed the records read")
        return self


class PipelineRun(Record):
    run_id: UUID
    job: Text
    environment: Environment
    mode: Mode
    scope: Annotated[dict[Text, JsonValue], Field(min_length=1)]
    status: Literal["running", "succeeded", "no_change", "partial", "failed", "deferred", "disabled", "cancelled"]
    started_at: AwareDatetime
    counters: RunCounters
    contract_version: Text
    coverage_policy_version: Text
    finished_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def terminal_time(self) -> PipelineRun:
        if (self.status == "running") != (self.finished_at is None):
            raise ValueError("Terminal runs require a finish time; running runs have none")
        return self


class Checkpoint(Record):
    environment: Environment
    job: Text
    scope_key: Text
    cursor: JsonValue
    committed_run_id: UUID
    committed_at: AwareDatetime


class ValidationIssue(Record):
    issue_id: UUID
    run_id: UUID
    dataset: Text
    record_key: tuple[JsonValue, ...] | None = None
    observation_id: UUID | None = None
    severity: Literal["error", "warning"]
    code: Text
    message: Text
    disposition: Literal["held", "rejected", "resolved"]
    resolution: Text | None = None
    resolved_by: Text | None = None

    @model_validator(mode="after")
    def resolution_recorded(self) -> ValidationIssue:
        if self.disposition == "resolved" and (self.resolution is None or self.resolved_by is None):
            raise ValueError("Resolved issues require a decision and actor")
        return self


class ModelVersion(Record):
    model_id: Id
    version: Text
    model_type: Text
    active: StrictBool
    created_at: AwareDatetime


class Prediction(Record):
    prediction_id: Id
    player_id: Id
    model_id: Id
    target_season: Season
    input_features: dict[Text, JsonValue]
    created_at: AwareDatetime


@dataclass(frozen=True)
class Reference:
    field: str
    target: str


@dataclass(frozen=True)
class RecordDefinition:
    model: type[Record]
    key_fields: tuple[str, ...]
    grain: str
    references: tuple[Reference, ...] = ()
    append_only: bool = False
    unique_keys: tuple[tuple[str, ...], ...] = ()

    def key(self, record: Record) -> tuple[Any, ...]:
        return tuple(getattr(record, field) for field in self.key_fields)

    def json_key(self, record: Record) -> tuple[JsonValue, ...]:
        """Manifest keys use ISO timestamp/UUID strings and JSON member arrays."""
        payload = record.model_dump(mode="json")
        return tuple(payload[field] for field in self.key_fields)


PLAYER_SEASON_REFS = (Reference("player_id", "player_profiles"), Reference("season", "seasons"), Reference("team_id", "teams"))
PLAYER_SEASON_KEY = ("source", "player_id", "season", "game_type", "team_scope", "team_id")
TEAM_SEASON_REFS = (Reference("team_id", "teams"), Reference("season", "seasons"))
ENTITY_TARGETS = MappingProxyType({"player": "player_profiles", "team": "teams", "franchise": "franchises", "game": "games", "contract": "contracts"})


RECORD_DEFINITIONS: Mapping[str, RecordDefinition] = MappingProxyType({
    "franchises": RecordDefinition(Franchise, ("franchise_id",), "One canonical franchise"),
    "teams": RecordDefinition(Team, ("team_id",), "One canonical team identity", (Reference("franchise_id", "franchises"),), unique_keys=(("nhl_team_id",),)),
    "seasons": RecordDefinition(SeasonRecord, ("season",), "One NHL season start year"),
    "team_seasons": RecordDefinition(TeamSeason, ("team_id", "season"), "One historical team-season identity", TEAM_SEASON_REFS + (Reference("franchise_id", "franchises"),)),
    "player_profiles": RecordDefinition(PlayerProfile, ("player_id",), "One canonical player identity", unique_keys=(("nhl_player_id",),)),
    "memberships": RecordDefinition(Membership, ("membership_id",), "One supported player-team membership episode", PLAYER_SEASON_REFS),
    "source_mappings": RecordDefinition(SourceMapping, ("source", "entity_type", "source_id"), "One source identifier mapped to one canonical entity"),
    "contracts": RecordDefinition(Contract, ("contract_id",), "One signed agreement", (Reference("player_id", "player_profiles"), Reference("signing_team_id", "teams"), Reference("start_season", "seasons"), Reference("end_season", "seasons"))),
    "contract_seasons": RecordDefinition(ContractSeason, ("contract_id", "season"), "One contract's terms for one season", (Reference("contract_id", "contracts"), Reference("player_id", "player_profiles"), Reference("season", "seasons"), Reference("owning_team_id", "teams"))),
    "basic_stats": RecordDefinition(BasicStats, PLAYER_SEASON_KEY + ("stat_kind",), "One source/player/season/game-type/team-scope/stat-kind", PLAYER_SEASON_REFS),
    "transactions": RecordDefinition(Transaction, ("source", "source_id"), "One current/recent source transaction with all participants", (Reference("from_team_id", "teams"), Reference("to_team_id", "teams"))),
    "roster_state": RecordDefinition(RosterState, ("player_id",), "One supported current state per player", (Reference("player_id", "player_profiles"), Reference("team_id", "teams"), Reference("override_id", "roster_overrides"))),
    "roster_observations": RecordDefinition(RosterObservation, ("snapshot_id", "player_id", "team_id"), "One observed roster membership within a source snapshot", (Reference("player_id", "player_profiles"), Reference("team_id", "teams")), append_only=True),
    "roster_overrides": RecordDefinition(RosterOverride, ("override_id",), "One dated manual roster decision", (Reference("player_id", "player_profiles"), Reference("team_id", "teams"))),
    "games": RecordDefinition(Game, ("game_id",), "One game; NHL game ID is an additional unique source identity", (Reference("season", "seasons"), Reference("home_team_id", "teams"), Reference("away_team_id", "teams")), unique_keys=(("nhl_game_id",),)),
    "game_stats": RecordDefinition(GameStats, ("game_id", "team_id", "entity_type", "entity_id"), "One player/team boxscore row per game", (Reference("game_id", "games"), Reference("team_id", "teams"))),
    "game_events": RecordDefinition(GameEvent, ("source", "game_id", "event_id"), "One ordered source event within a game", (Reference("game_id", "games"), Reference("player_id", "player_profiles"), Reference("team_id", "teams"))),
    "moneypuck_skater_stats": RecordDefinition(SkaterAdvanced, PLAYER_SEASON_KEY + ("situation",), "One source/skater/season/game-type/team-scope/situation", PLAYER_SEASON_REFS),
    "moneypuck_goalie_stats": RecordDefinition(GoalieAdvanced, PLAYER_SEASON_KEY + ("situation",), "One source/goalie/season/game-type/team-scope/situation", PLAYER_SEASON_REFS),
    "moneypuck_team_stats": RecordDefinition(TeamAdvanced, ("source", "team_id", "season", "game_type", "situation"), "One source/team/season/game-type/situation", TEAM_SEASON_REFS),
    "moneypuck_line_stats": RecordDefinition(LineAdvanced, ("source", "team_id", "season", "game_type", "situation", "player_ids"), "One source/team/season/game-type/situation/distinct sorted player combination", TEAM_SEASON_REFS),
    "shots": RecordDefinition(Shot, ("source", "game_id", "shot_id"), "One source shot event within a game", (Reference("game_id", "games"), Reference("season", "seasons"), Reference("player_id", "player_profiles"), Reference("team_id", "teams"))),
    "edge_summaries": RecordDefinition(EdgeSeason, ("entity_type", "entity_id", "season", "game_type", "observed_at"), "One dated EDGE season observation, not a derived summary", (Reference("season", "seasons"),), append_only=True),
    "edge_games": RecordDefinition(EdgeGame, ("entity_type", "entity_id", "game_id", "observed_at"), "One available dated EDGE entity/game observation", (Reference("season", "seasons"), Reference("game_id", "games")), append_only=True),
    "edge_events": RecordDefinition(EdgeEvent, ("entity_type", "entity_id", "season", "game_type", "event_id", "observed_at"), "One dated EDGE selected-event observation", (Reference("season", "seasons"), Reference("game_id", "games")), append_only=True),
    "datasets": RecordDefinition(DatasetVersion, ("dataset_id", "version"), "One immutable dataset manifest with exact input revisions", append_only=True),
    "source_observations": RecordDefinition(SourceObservation, ("observation_id",), "One immutable dated source response with digest and transformation version", append_only=True),
    "pipeline_runs": RecordDefinition(PipelineRun, ("run_id",), "One requested job execution"),
    "checkpoints": RecordDefinition(Checkpoint, ("environment", "job", "scope_key"), "One committed progress cursor per environment/job/scope", (Reference("committed_run_id", "pipeline_runs"),)),
    "validation_issues": RecordDefinition(ValidationIssue, ("issue_id",), "One reviewable validation or identity issue", (Reference("run_id", "pipeline_runs"), Reference("observation_id", "source_observations"))),
    "model_versions": RecordDefinition(ModelVersion, ("model_id",), "One preserved existing model version; activation changes are revisions"),
    "predictions": RecordDefinition(Prediction, ("prediction_id",), "One preserved existing player prediction", (Reference("player_id", "player_profiles"), Reference("model_id", "model_versions")), append_only=True),
})


def validate_record(dataset: str, payload: Mapping[str, Any] | str | bytes) -> Record:
    """Validate without database access, field coercion, or mutation of the input.

    Python mappings use date/datetime/UUID objects. JSON input uses their ISO/UUID
    encodings. Dates and timestamps stay distinct; UTC normalization is explicit.
    """
    model = RECORD_DEFINITIONS[dataset].model
    record = model.model_validate_json(payload) if isinstance(payload, (str, bytes)) else model.model_validate(payload)
    if isinstance(record, (SourceObservation, ValidationIssue)) and record.dataset not in RECORD_DEFINITIONS:
        raise ValueError("Unknown observation/issue dataset")
    if isinstance(record, DatasetVersion):
        identities = []
        for item in record.input_revisions:
            definition = RECORD_DEFINITIONS.get(item.dataset)
            if definition is None or len(item.record_key) != len(definition.key_fields):
                raise ValueError("Unknown dataset input or wrong key length")
            identities.append((item.dataset, repr(item.record_key), item.revision))
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate dataset input revision")
    if isinstance(record, (Shot, GameEvent)):
        if (record.x is None) != (record.y is None):
            raise ValueError("Coordinates must be supplied as a pair")
        if record.x is not None and record.coordinate_system is None:
            raise ValueError("Coordinates require a source coordinate-system definition")
    return record


def validate_batch(records: tuple[tuple[str, Record], ...],
                   lookup: Callable[[str, tuple[Any, ...]], Record | None]) -> None:
    """Check identities/relationships against a supplied lookup or this batch.

    ``lookup(dataset, key)`` returns a normalized Record or None from a consistent
    accepted view. This verifies contracts against test doubles before databases
    are selected; persistence constraints remain an integration responsibility.
    """
    indexed: dict[tuple[str, tuple[Any, ...]], Record] = {}
    unique: set[tuple[Any, ...]] = set()
    for dataset, record in records:
        definition = RECORD_DEFINITIONS[dataset]
        if type(record) is not definition.model:
            raise ValueError("Record model does not match its dataset")
        # Revalidate even if a caller used Pydantic's unchecked model_construct.
        validate_record(dataset, record.model_dump())
        identity = dataset, definition.key(record)
        if identity in indexed:
            raise ValueError(f"Duplicate record identity: {identity}")
        indexed[identity] = record
        for fields in definition.unique_keys:
            values = tuple(getattr(record, field) for field in fields)
            if None not in values:
                unique_key = dataset, fields, values
                if unique_key in unique:
                    raise ValueError(f"Duplicate source identity: {unique_key}")
                unique.add(unique_key)

    def resolve(target: str, key: tuple[Any, ...]) -> Record:
        found = indexed.get((target, key))
        if found is None:
            found = lookup(target, key)
        if found is None:
            raise ValueError(f"Unresolved reference: {target} {key}")
        definition = RECORD_DEFINITIONS[target]
        if type(found) is not definition.model or definition.key(found) != key:
            raise ValueError("Lookup returned a different record identity")
        return found

    for dataset, record in records:
        for ref in RECORD_DEFINITIONS[dataset].references:
            value = getattr(record, ref.field)
            if value is not None:
                resolve(ref.target, (value,))
        if isinstance(record, SourceMapping):
            resolve(ENTITY_TARGETS[record.entity_type], (record.canonical_id,))
        if isinstance(record, (GameStats, EdgeSeason)):
            resolve(ENTITY_TARGETS[record.entity_type], (record.entity_id,))
        if isinstance(record, Transaction):
            for participant in record.participants:
                resolve("player_profiles", (participant.player_id,))
        if isinstance(record, LineAdvanced):
            for player_id in record.player_ids:
                resolve("player_profiles", (player_id,))
        if isinstance(record, RosterState):
            for observation_id in record.evidence:
                resolve("source_observations", (observation_id,))
            if record.override_id is not None:
                override = resolve("roster_overrides", (record.override_id,))
                if (override.player_id, override.status, override.team_id) != (record.player_id, record.status, record.team_id):
                    raise ValueError("Roster state differs from its override")
                if record.effective_date is None or record.effective_date < override.effective_from or (override.effective_to is not None and record.effective_date > override.effective_to):
                    raise ValueError("Roster state is outside its override interval")
        if isinstance(record, ContractSeason):
            contract = resolve("contracts", (record.contract_id,))
            if contract.player_id != record.player_id or not contract.start_season <= record.season <= contract.end_season:
                raise ValueError("Contract-season owner or range differs from the agreement")
        if isinstance(record, (Shot, GameStats, GameEvent, EdgeGame, EdgeEvent)) and record.game_id is not None:
            game = resolve("games", (record.game_id,))
            if hasattr(record, "season") and (record.season, record.game_type) != (game.season, game.game_type):
                raise ValueError("Dependent record differs from its game season/type")
            team_id = getattr(record, "team_id", None)
            if team_id is not None and team_id not in (game.home_team_id, game.away_team_id):
                raise ValueError("Dependent record team did not participate in the game")
            if isinstance(record, GameStats) and record.entity_type == "team" and record.entity_id != record.team_id:
                raise ValueError("Team boxscore entity differs from its team")

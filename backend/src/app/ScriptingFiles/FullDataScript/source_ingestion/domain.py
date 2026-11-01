"""Immutable source snapshots, normalization layouts, and stage results."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum, auto


class PlayerKind(StrEnum):
    SKATER = auto()
    GOALIE = auto()


@dataclass(slots=True, kw_only=True, frozen=True)
class MetricSpec:
    column: str
    source_field: str
    integer: bool = False


@dataclass(slots=True, kw_only=True, frozen=True)
class StatLayout:
    table: str
    metrics: tuple[MetricSpec, ...]
    advanced: bool


@dataclass(slots=True, kw_only=True, frozen=True)
class StatRow:
    kind: PlayerKind
    external_id: str
    season: int
    name: str
    position: str | None
    teams: tuple[str, ...]
    game_type: int
    situation: str | None
    metrics: tuple[int | float | None, ...]
    source_row_hash: str
    extra_metrics_json: str | None = None
    shoots_catches: str | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class Team:
    abbreviation: str
    name: str | None = None
    city: str | None = None
    nhl_team_id: int | None = None
    nhl_franchise_id: int | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class Player:
    external_id: str
    name: str
    birth_date: str | None = None
    position: str | None = None
    shoots_catches: str | None = None
    nationality: str | None = None
    source_slug: str | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class RosterPlayer:
    team: str
    player: Player
    birth_country: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class Game:
    external_id: int
    game_date: date
    away_team: str
    home_team: str
    start_time_utc: str | None
    venue: str | None
    game_state: str | None
    away_score: int | None
    home_score: int | None


@dataclass(slots=True, kw_only=True, frozen=True)
class WriteCounts:
    records_read: int
    records_created: int
    records_updated: int
    records_skipped: int


@dataclass(slots=True, kw_only=True, frozen=True)
class MoneyPuckSummary:
    players: int
    skater: int
    goalie: int
    counts: WriteCounts


@dataclass(slots=True, kw_only=True, frozen=True)
class NhlStatsSummary:
    skater: int
    goalie: int
    team_stints: int
    counts: WriteCounts


@dataclass(slots=True, kw_only=True, frozen=True)
class RosterSummary:
    teams: int
    active_players: int


@dataclass(slots=True, kw_only=True, frozen=True)
class ScheduleSummary:
    games: int
    counts: WriteCounts


@dataclass(slots=True, kw_only=True, frozen=True)
class DataQualityReport:
    source: str
    records_read: int
    records_valid: int
    duplicate_records: int
    seasons: tuple[int, ...]

    @property
    def duplicate_ratio(self) -> float:
        return (
            self.duplicate_records / self.records_read if self.records_read > 0 else 0.0
        )


def serialize_summary(
    summary: MoneyPuckSummary | NhlStatsSummary | RosterSummary | ScheduleSummary,
) -> dict[str, int | str]:
    from app.ScriptingFiles.FullDataScript.source_ingestion.util import (
        serialize_summary as serialize_report,
    )

    return serialize_report(summary)


def build_moneypuck_skater_layout() -> StatLayout:
    return StatLayout(
        table="skater_advanced_season_stats",
        advanced=True,
        metrics=(
            MetricSpec(
                column="games_played", source_field="games_played", integer=True
            ),
            MetricSpec(
                column="ice_time_seconds", source_field="icetime", integer=False
            ),
            MetricSpec(column="shifts", source_field="shifts", integer=True),
            MetricSpec(column="game_score", source_field="gameScore", integer=False),
            MetricSpec(
                column="individual_points", source_field="I_F_points", integer=True
            ),
            MetricSpec(
                column="individual_goals", source_field="I_F_goals", integer=True
            ),
            MetricSpec(
                column="individual_primary_assists",
                source_field="I_F_primaryAssists",
                integer=True,
            ),
            MetricSpec(
                column="individual_secondary_assists",
                source_field="I_F_secondaryAssists",
                integer=True,
            ),
            MetricSpec(
                column="individual_expected_goals",
                source_field="I_F_xGoals",
                integer=False,
            ),
            MetricSpec(
                column="individual_shots_on_goal",
                source_field="I_F_shotsOnGoal",
                integer=True,
            ),
            MetricSpec(
                column="individual_unblocked_attempts",
                source_field="I_F_unblockedShotAttempts",
                integer=True,
            ),
            MetricSpec(
                column="on_ice_expected_goals_pct",
                source_field="onIce_xGoalsPercentage",
                integer=False,
            ),
            MetricSpec(
                column="shots_blocked",
                source_field="shotsBlockedByPlayer",
                integer=True,
            ),
            MetricSpec(column="takeaways", source_field="I_F_takeaways", integer=True),
            MetricSpec(column="giveaways", source_field="I_F_giveaways", integer=True),
            MetricSpec(column="penalties", source_field="penalties", integer=True),
            MetricSpec(
                column="penalties_drawn", source_field="penaltiesDrawn", integer=True
            ),
            MetricSpec(
                column="offensive_zone_shift_starts",
                source_field="I_F_oZoneShiftStarts",
                integer=True,
            ),
            MetricSpec(
                column="defensive_zone_shift_starts",
                source_field="I_F_dZoneShiftStarts",
                integer=True,
            ),
            MetricSpec(
                column="neutral_zone_shift_starts",
                source_field="I_F_neutralZoneShiftStarts",
                integer=True,
            ),
        ),
    )


def build_moneypuck_goalie_layout() -> StatLayout:
    return StatLayout(
        table="goalie_advanced_season_stats",
        advanced=True,
        metrics=(
            MetricSpec(
                column="games_played", source_field="games_played", integer=True
            ),
            MetricSpec(
                column="ice_time_seconds", source_field="icetime", integer=False
            ),
            MetricSpec(
                column="expected_goals_against", source_field="xGoals", integer=False
            ),
            MetricSpec(column="goals_against", source_field="goals", integer=False),
            MetricSpec(
                column="unblocked_shot_attempts",
                source_field="unblocked_shot_attempts",
                integer=True,
            ),
            MetricSpec(
                column="blocked_shot_attempts",
                source_field="blocked_shot_attempts",
                integer=True,
            ),
            MetricSpec(
                column="expected_rebounds", source_field="xRebounds", integer=False
            ),
            MetricSpec(column="rebounds", source_field="rebounds", integer=True),
            MetricSpec(
                column="expected_freezes", source_field="xFreeze", integer=False
            ),
            MetricSpec(column="freezes", source_field="freeze", integer=True),
            MetricSpec(
                column="expected_shots_on_goal", source_field="xOnGoal", integer=False
            ),
            MetricSpec(column="shots_on_goal", source_field="ongoal", integer=True),
            MetricSpec(
                column="flurry_adjusted_expected_goals",
                source_field="flurryAdjustedxGoals",
                integer=False,
            ),
            MetricSpec(
                column="low_danger_shots", source_field="lowDangerShots", integer=True
            ),
            MetricSpec(
                column="medium_danger_shots",
                source_field="mediumDangerShots",
                integer=True,
            ),
            MetricSpec(
                column="high_danger_shots", source_field="highDangerShots", integer=True
            ),
            MetricSpec(
                column="low_danger_expected_goals",
                source_field="lowDangerxGoals",
                integer=False,
            ),
            MetricSpec(
                column="medium_danger_expected_goals",
                source_field="mediumDangerxGoals",
                integer=False,
            ),
            MetricSpec(
                column="high_danger_expected_goals",
                source_field="highDangerxGoals",
                integer=False,
            ),
            MetricSpec(
                column="low_danger_goals", source_field="lowDangerGoals", integer=True
            ),
            MetricSpec(
                column="medium_danger_goals",
                source_field="mediumDangerGoals",
                integer=True,
            ),
            MetricSpec(
                column="high_danger_goals", source_field="highDangerGoals", integer=True
            ),
        ),
    )


def build_nhl_skater_layout() -> StatLayout:
    return StatLayout(
        table="skater_season_stats",
        advanced=False,
        metrics=(
            MetricSpec(column="games_played", source_field="gamesPlayed", integer=True),
            MetricSpec(column="goals", source_field="goals", integer=True),
            MetricSpec(column="assists", source_field="assists", integer=True),
            MetricSpec(column="points", source_field="points", integer=True),
            MetricSpec(column="plus_minus", source_field="plusMinus", integer=True),
            MetricSpec(
                column="penalty_minutes", source_field="penaltyMinutes", integer=True
            ),
            MetricSpec(column="power_play_goals", source_field="ppGoals", integer=True),
            MetricSpec(
                column="power_play_points", source_field="ppPoints", integer=True
            ),
            MetricSpec(
                column="short_handed_goals", source_field="shGoals", integer=True
            ),
            MetricSpec(column="shots", source_field="shots", integer=True),
            MetricSpec(
                column="shooting_percentage", source_field="shootingPct", integer=False
            ),
        ),
    )


def build_nhl_goalie_layout() -> StatLayout:
    return StatLayout(
        table="goalie_season_stats",
        advanced=False,
        metrics=(
            MetricSpec(column="games_played", source_field="gamesPlayed", integer=True),
            MetricSpec(column="wins", source_field="wins", integer=True),
            MetricSpec(column="losses", source_field="losses", integer=True),
            MetricSpec(column="overtime_losses", source_field="otLosses", integer=True),
            MetricSpec(
                column="shots_against", source_field="shotsAgainst", integer=True
            ),
            MetricSpec(column="saves", source_field="saves", integer=True),
            MetricSpec(column="save_percentage", source_field="savePct", integer=False),
            MetricSpec(
                column="goals_against", source_field="goalsAgainst", integer=True
            ),
            MetricSpec(
                column="goals_against_average",
                source_field="goalsAgainstAverage",
                integer=False,
            ),
            MetricSpec(column="shutouts", source_field="shutouts", integer=True),
            MetricSpec(
                column="time_on_ice_seconds", source_field="timeOnIce", integer=True
            ),
        ),
    )


def select_stat_layout(kind: PlayerKind, *, advanced: bool) -> StatLayout:
    if advanced:
        return (
            build_moneypuck_skater_layout()
            if kind == PlayerKind.SKATER
            else build_moneypuck_goalie_layout()
        )
    return (
        build_nhl_skater_layout()
        if kind == PlayerKind.SKATER
        else build_nhl_goalie_layout()
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SourceHttpOptions:
    json_timeout: float = 30.0
    csv_timeout: float = 60.0
    retry_total: int = 4
    retry_backoff: float = 0.6
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)
    user_agent: str = "TradeValue/1.0 (NHL analytics data ingestion)"

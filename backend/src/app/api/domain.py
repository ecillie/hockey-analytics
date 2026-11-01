"""Immutable API read results and query options."""

from dataclasses import dataclass
from datetime import date
from typing import Literal, TypedDict


@dataclass(slots=True, kw_only=True, frozen=True)
class IdentityRow:
    id: int
    first_name: str
    last_name: str
    full_name: str
    birth_date: date | None
    age: int | None
    primary_position: str | None
    shoots_catches: str | None
    nationality: str | None
    active: bool
    roster_status: str
    team_id: int | None
    nhl_team_id: int | None
    abbreviation: str | None
    team_name: str | None
    team_city: str | None
    team_active: bool | None


@dataclass(slots=True, kw_only=True, frozen=True)
class SummaryRow:
    id: int
    first_name: str
    last_name: str
    full_name: str
    birth_date: date | None
    age: int | None
    primary_position: str | None
    shoots_catches: str | None
    nationality: str | None
    active: bool
    roster_status: str
    team_id: int | None
    nhl_team_id: int | None
    abbreviation: str | None
    team_name: str | None
    team_city: str | None
    team_active: bool | None
    games_played: int | None
    goals: int | None
    assists: int | None
    points: int | None
    plus_minus: int | None
    penalty_minutes: int | None
    power_play_goals: int | None
    power_play_points: int | None
    short_handed_goals: int | None
    shots: int | None
    shifts: int | None
    takeaways: int | None
    giveaways: int | None
    shots_blocked: int | None
    penalties: int | None
    penalties_drawn: int | None
    cap_hit_cents: int | None
    shooting_percentage: float | None
    ice_time_seconds: float | None
    game_score: float | None
    game_score_per_60: float | None
    individual_expected_goals: float | None
    expected_goals_per_60: float | None
    on_ice_expected_goals_pct: float | None
    hockey_value: float | None
    projected_hockey_value: float | None
    gs60_above_replacement: float | None
    season: int
    model_version: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class TeamRow:
    id: int
    nhl_team_id: int | None
    abbreviation: str | None
    team_name: str | None
    team_city: str | None
    team_active: bool | None


@dataclass(slots=True, kw_only=True, frozen=True)
class SeasonRow:
    start_year: int
    end_year: int
    label: str
    salary_cap_cents: int | None


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractRow:
    id: int
    player_id: int
    signed_on: date | None
    start_season: int
    end_season: int
    term_years: int
    contract_type: str | None
    expiry_status: str | None
    total_value_cents: int | None
    average_value_cents: int | None
    is_entry_level: bool
    signing_team_id: int | None
    signing_nhl_team_id: int | None
    signing_abbreviation: str | None
    signing_team_name: str | None
    signing_team_city: str | None
    signing_team_active: bool | None


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractSeasonRow:
    team_id: int | None
    nhl_team_id: int | None
    abbreviation: str | None
    team_name: str | None
    team_city: str | None
    team_active: bool | None
    season_start_year: int
    base_salary_cents: int | None
    signing_bonus_cents: int | None
    performance_bonus_cents: int | None
    total_cash_cents: int | None
    cap_hit_cents: int
    cap_percentage: float | None
    is_slide: bool


@dataclass(slots=True, kw_only=True, frozen=True)
class GoalieRow:
    games_played: int | None
    wins: int | None
    losses: int | None
    overtime_losses: int | None
    shots_against: int | None
    saves: int | None
    goals_against: int | None
    time_on_ice_seconds: int | None
    shutouts: int | None
    save_percentage: float | None
    gaa: float | None
    xga: float | None
    ga: float | None
    gsae: float | None


@dataclass(slots=True, kw_only=True, frozen=True)
class CapRow:
    salary_cap_cents: int | None
    active_cap: int
    ltir_cap: int
    minors_cap: int
    total_cap: int


type PlayerSort = Literal[
    "name",
    "team",
    "gamesPlayed",
    "goals",
    "assists",
    "points",
    "gameScore",
    "gameScorePer60",
    "hockeyValue",
    "capHitCents",
]
type SortOrder = Literal["asc", "desc"]


@dataclass(slots=True, kw_only=True, frozen=True)
class PlayerQuery:
    season: int
    team: str | None = None
    position: str | None = None
    roster_status: str | None = None
    search: str | None = None
    sort: PlayerSort = "hockeyValue"
    order: SortOrder = "desc"
    page: int = 1
    page_size: int = 25


@dataclass(slots=True, kw_only=True, frozen=True)
class PlayerPage:
    rows: tuple[SummaryRow, ...]
    total: int


@dataclass(slots=True, kw_only=True, frozen=True)
class SummarySelection:
    season: int
    where: str = "TRUE"
    bindings: tuple[tuple[str, str | int], ...] = ()
    order: str = "id ASC"
    limit: int | None = None
    offset: int | None = None


class TeamSummaryData(TypedDict):
    id: int
    nhlTeamId: int | None
    abbreviation: str | None
    name: str | None
    city: str | None
    active: bool | None


class TeamData(TeamSummaryData):
    rosterCounts: dict[str, int]


class PlayerIdentityData(TypedDict):
    id: int
    firstName: str
    lastName: str
    fullName: str
    birthDate: date | None
    age: int | None
    primaryPosition: str | None
    shootsCatches: str | None
    nationality: str | None
    active: bool
    rosterStatus: str
    team: TeamSummaryData | None


class PlayerSummaryData(PlayerIdentityData):
    season: int
    gamesPlayed: int | None
    goals: int | None
    assists: int | None
    points: int | None
    toiSeconds: int | None
    gameScore: float | None
    gameScorePer60: float | None
    hockeyValue: float | None
    projectedNextSeasonHockeyValue: float | None
    capHitCents: int | None


class TraditionalSkaterStatsData(TypedDict):
    gamesPlayed: int | None
    goals: int | None
    assists: int | None
    points: int | None
    plusMinus: int | None
    penaltyMinutes: int | None
    powerPlayGoals: int | None
    powerPlayPoints: int | None
    shortHandedGoals: int | None
    shots: int | None
    shootingPercentage: float | None


class AdvancedSkaterStatsData(TypedDict):
    situation: str
    iceTimeSeconds: int | None
    shifts: int | None
    gameScore: float | None
    gameScorePer60: float | None
    individualExpectedGoals: float | None
    expectedGoalsPer60: float | None
    onIceExpectedGoalsPercentage: float | None
    takeaways: int | None
    giveaways: int | None
    shotsBlocked: int | None
    penalties: int | None
    penaltiesDrawn: int | None


class GoalieStatsData(TypedDict):
    gamesPlayed: int | None
    wins: int | None
    losses: int | None
    overtimeLosses: int | None
    shotsAgainst: int | None
    saves: int | None
    savePercentage: float | None
    goalsAgainstAverage: float | None
    shutouts: int | None
    timeOnIceSeconds: int | None
    expectedGoalsAgainst: float | None
    goalsSavedAboveExpected: float | None


class PlayerStatsData(TypedDict):
    playerId: int
    season: int
    team: TeamSummaryData | None
    traditional: TraditionalSkaterStatsData | None
    advanced: AdvancedSkaterStatsData | None
    goalie: GoalieStatsData | None


class SeasonHistoryRowData(TypedDict):
    season: int
    team: TeamSummaryData | None
    gamesPlayed: int | None
    goals: int | None
    assists: int | None
    points: int | None
    gameScorePer60: float | None
    hockeyValue: float | None


class HockeyValueData(TypedDict):
    playerId: int
    season: int
    hockeyValue: float | None
    projectedNextSeasonHockeyValue: float | None
    gameScorePer60AboveReplacement: float | None
    toiHours: float | None
    modelVersion: str | None


class HockeyValueHistoryPointData(TypedDict):
    season: int
    hockeyValue: float | None


class ContractSeasonData(TypedDict):
    season: int
    owningTeam: TeamSummaryData | None
    baseSalaryCents: int | None
    signingBonusCents: int | None
    performanceBonusCents: int | None
    totalCashCents: int | None
    capHitCents: int
    capPercentage: float | None
    isSlide: bool


class ContractData(TypedDict):
    id: int
    playerId: int
    signingTeam: TeamSummaryData | None
    signedOn: date | None
    startSeason: int
    endSeason: int
    termYears: int
    contractType: str | None
    expiryStatus: str | None
    totalValueCents: int | None
    averageValueCents: int | None
    isEntryLevel: bool
    seasons: list[ContractSeasonData]


class PaginationData(TypedDict):
    page: int
    pageSize: int
    totalItems: int
    totalPages: int


class PaginatedPlayersData(TypedDict):
    data: list[PlayerSummaryData]
    pagination: PaginationData


class TeamRosterResponseData(TypedDict):
    team: TeamSummaryData
    season: int
    status: str | None
    players: list[PlayerSummaryData]


class TeamContractRowData(TypedDict):
    player: PlayerIdentityData
    contract: ContractData
    season: ContractSeasonData


class TeamContractsResponseData(TypedDict):
    team: TeamSummaryData
    season: int
    contracts: list[TeamContractRowData]


class TeamCapData(TypedDict):
    teamId: int
    season: int
    salaryCapCents: int | None
    activeRosterCapCents: int
    ltirCapCents: int
    minorsCapCents: int
    totalCommitmentsCents: int
    capSpaceCents: int | None
    calculationStatus: Literal["ESTIMATE", "AUTHORITATIVE"]


class AvailableSeasonData(TypedDict):
    startYear: int
    endYear: int
    label: str
    salaryCapCents: int | None


class SeasonInfoData(TypedDict):
    currentSeason: int
    availableSeasons: list[AvailableSeasonData]


class SearchResponseData(TypedDict):
    players: list[PlayerIdentityData]
    teams: list[TeamSummaryData]


class LeagueOverviewData(TypedDict):
    players: int
    goals: int
    gamesPlayed: int
    averageHockeyValue: float | None


class OverviewLeadersData(TypedDict):
    hockeyValue: list[PlayerSummaryData]
    points: list[PlayerSummaryData]
    goals: list[PlayerSummaryData]
    gameScorePer60: list[PlayerSummaryData]


class OverviewResponseData(TypedDict):
    season: int
    league: LeagueOverviewData
    leaders: OverviewLeadersData


class CompareRowData(TypedDict):
    player: PlayerIdentityData
    stats: PlayerStatsData
    value: HockeyValueData | None
    contract: ContractData | None


class CompareResponseData(TypedDict):
    season: int
    players: list[CompareRowData]

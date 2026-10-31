"""Application orchestration over an injected read repository."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from math import ceil

from app.api.domain import (
    ContractData,
    CompareResponseData,
    GoalieStatsData,
    HockeyValueData,
    HockeyValueHistoryPointData,
    OverviewResponseData,
    PaginatedPlayersData,
    PlayerStatsData,
    SearchResponseData,
    SeasonInfoData,
    TeamCapData,
    TeamContractsResponseData,
    TeamData,
    TeamRosterResponseData,
    TraditionalSkaterStatsData,
    AdvancedSkaterStatsData,
    TeamContractRowData,
    PlayerIdentityData,
    PlayerSummaryData,
    PlayerQuery,
    PlayerSort,
    SortOrder,
    SeasonHistoryRowData,
    SummaryRow,
    TeamSummaryData,
)
from app.api.errors import (
    CapUnavailable,
    InvalidSeason,
    PlayerNotFound,
    SeasonsUnavailable,
    TeamNotFound,
)
from app.api.policy import buried_relief_cents, latest_started_season
from app.api.repository import ApiRepository
from app.api.util import (
    contract_season_data,
    identity_data,
    player_team_data,
    summary_data,
    team_data,
    top_summaries,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class TradeValueService:
    repository: ApiRepository
    as_of: date = field(default_factory=date.today)

    @property
    def latest_started_season(self) -> int:
        return latest_started_season(self.as_of)

    def check_health(self) -> None:
        self.repository.check_health()

    def current_season(self) -> int:
        value = self.repository.current_season(self.latest_started_season)
        if value is None:
            raise SeasonsUnavailable()
        return value

    def require_season(self, season: int) -> None:
        if not self.repository.has_season(season, self.latest_started_season):
            raise InvalidSeason(season=season)

    def seasons(self) -> SeasonInfoData:
        rows = self.repository.seasons(self.latest_started_season)
        return {
            "currentSeason": self.current_season(),
            "availableSeasons": [
                {
                    "startYear": r.start_year,
                    "endYear": r.end_year,
                    "label": r.label,
                    "salaryCapCents": r.salary_cap_cents,
                }
                for r in rows
            ],
        }

    def player_identity(self, player_id: int) -> PlayerIdentityData:
        row = self.repository.player(player_id)
        if row is None:
            raise PlayerNotFound(player_id=player_id)
        return identity_data(row)

    def team_summary(self, team_id: int) -> TeamSummaryData:
        row = self.repository.team(team_id)
        if row is None:
            raise TeamNotFound(team_id=team_id)
        return team_data(row)

    def summary_for_player(self, player_id: int, season: int) -> SummaryRow | None:
        return self.repository.summary_for_player(player_id, season)

    def players(
        self,
        season: int,
        team: str | None,
        position: str | None,
        roster_status: str | None,
        search: str | None,
        sort: PlayerSort,
        order: SortOrder,
        page: int,
        page_size: int,
    ) -> PaginatedPlayersData:
        self.require_season(season)
        result = self.repository.players(
            PlayerQuery(
                season=season,
                team=team,
                position=position,
                roster_status=roster_status,
                search=search,
                sort=sort,
                order=order,
                page=page,
                page_size=page_size,
            )
        )
        return {
            "data": list(map(summary_data, result.rows)),
            "pagination": {
                "page": page,
                "pageSize": page_size,
                "totalItems": result.total,
                "totalPages": ceil(result.total / page_size),
            },
        }

    def teams(self) -> list[TeamSummaryData]:
        return list(map(team_data, self.repository.teams()))

    def team(self, team_id: int) -> TeamData:
        team = self.team_summary(team_id)
        counts = {status: 0 for status in ("ACTIVE", "MINORS", "LTIR", "UNKNOWN")}
        counts.update(self.repository.roster_counts(team_id))
        return {**team, "rosterCounts": counts}

    def roster(
        self, team_id: int, season: int, status: str | None
    ) -> TeamRosterResponseData:
        self.require_season(season)
        team = self.team_summary(team_id)
        rows = self.repository.roster(team_id, season, status)
        return {
            "team": team,
            "season": season,
            "status": status,
            "players": list(map(summary_data, rows)),
        }

    def player_stats(self, player_id: int, season: int) -> PlayerStatsData:
        self.require_season(season)
        self.player_identity(player_id)
        row = self.summary_for_player(player_id, season)
        if row is None:
            raise PlayerNotFound(player_id=player_id)
        traditional: TraditionalSkaterStatsData | None = None
        advanced: AdvancedSkaterStatsData | None = None
        if row.primary_position != "G":
            if row.games_played is not None:
                traditional = {
                    "gamesPlayed": row.games_played,
                    "goals": row.goals,
                    "assists": row.assists,
                    "points": row.points,
                    "plusMinus": row.plus_minus,
                    "penaltyMinutes": row.penalty_minutes,
                    "powerPlayGoals": row.power_play_goals,
                    "powerPlayPoints": row.power_play_points,
                    "shortHandedGoals": row.short_handed_goals,
                    "shots": row.shots,
                    "shootingPercentage": row.shooting_percentage,
                }
            if row.ice_time_seconds is not None:
                advanced = {
                    "situation": "all",
                    "iceTimeSeconds": round(row.ice_time_seconds),
                    "shifts": row.shifts,
                    "gameScore": row.game_score,
                    "gameScorePer60": row.game_score_per_60,
                    "individualExpectedGoals": row.individual_expected_goals,
                    "expectedGoalsPer60": row.expected_goals_per_60,
                    "onIceExpectedGoalsPercentage": row.on_ice_expected_goals_pct,
                    "takeaways": row.takeaways,
                    "giveaways": row.giveaways,
                    "shotsBlocked": row.shots_blocked,
                    "penalties": row.penalties,
                    "penaltiesDrawn": row.penalties_drawn,
                }
        goalie = (
            self._goalie_stats(player_id, season)
            if row.primary_position == "G"
            else None
        )
        return {
            "playerId": player_id,
            "season": season,
            "team": player_team_data(row),
            "traditional": traditional,
            "advanced": advanced,
            "goalie": goalie,
        }

    def _goalie_stats(self, player_id: int, season: int) -> GoalieStatsData | None:
        row = self.repository.goalie(player_id, season)
        if row is None or row.games_played is None:
            return None
        return {
            "gamesPlayed": row.games_played,
            "wins": row.wins,
            "losses": row.losses,
            "overtimeLosses": row.overtime_losses,
            "shotsAgainst": row.shots_against,
            "saves": row.saves,
            "savePercentage": row.save_percentage,
            "goalsAgainstAverage": row.gaa,
            "shutouts": row.shutouts,
            "timeOnIceSeconds": row.time_on_ice_seconds,
            "expectedGoalsAgainst": row.xga,
            "goalsSavedAboveExpected": row.gsae,
        }

    def hockey_value(self, player_id: int, season: int | None) -> HockeyValueData:
        season = season if season is not None else self.current_season()
        self.require_season(season)
        self.player_identity(player_id)
        row = self.summary_for_player(player_id, season)
        return {
            "playerId": player_id,
            "season": season,
            "hockeyValue": row.hockey_value if row is not None else None,
            "projectedNextSeasonHockeyValue": row.projected_hockey_value
            if row is not None
            else None,
            "gameScorePer60AboveReplacement": row.gs60_above_replacement
            if row is not None
            else None,
            "toiHours": row.ice_time_seconds / 3600.0
            if row is not None and row.ice_time_seconds is not None
            else None,
            "modelVersion": row.model_version if row is not None else None,
        }

    def player_seasons(self, player_id: int) -> list[SeasonHistoryRowData]:
        self.player_identity(player_id)
        seasons = self.repository.player_seasons(player_id)
        result: list[SeasonHistoryRowData] = []
        for season in seasons:
            row = self.summary_for_player(player_id, season)
            if row is not None:
                result.append(
                    {
                        "season": season,
                        "team": player_team_data(row),
                        "gamesPlayed": row.games_played,
                        "goals": row.goals,
                        "assists": row.assists,
                        "points": row.points,
                        "gameScorePer60": row.game_score_per_60,
                        "hockeyValue": row.hockey_value,
                    }
                )
        return result

    def value_history(self, player_id: int) -> list[HockeyValueHistoryPointData]:
        return [
            {"season": row["season"], "hockeyValue": row["hockeyValue"]}
            for row in self.player_seasons(player_id)
        ]

    def leaders(
        self, season: int, position: str | None, team: str | None, limit: int
    ) -> list[PlayerSummaryData]:
        self.require_season(season)
        return list(
            map(summary_data, self.repository.leaders(season, position, team, limit))
        )

    def contract(
        self, player_id: int, current_season: int | None = None
    ) -> ContractData | None:
        self.player_identity(player_id)
        current_season = (
            current_season if current_season is not None else self.current_season()
        )
        row = self.repository.contract(player_id, current_season)
        if row is None:
            return None
        signing_team: TeamSummaryData | None = None
        if row.signing_team_id is not None:
            signing_team = {
                "id": row.signing_team_id,
                "nhlTeamId": row.signing_nhl_team_id,
                "abbreviation": row.signing_abbreviation,
                "name": row.signing_team_name,
                "city": row.signing_team_city,
                "active": row.signing_team_active,
            }
        seasons = [
            contract_season_data(r) for r in self.repository.contract_seasons(row.id)
        ]
        return {
            "id": row.id,
            "playerId": row.player_id,
            "signingTeam": signing_team,
            "signedOn": row.signed_on,
            "startSeason": row.start_season,
            "endSeason": row.end_season,
            "termYears": row.term_years,
            "contractType": row.contract_type,
            "expiryStatus": row.expiry_status,
            "totalValueCents": row.total_value_cents,
            "averageValueCents": row.average_value_cents,
            "isEntryLevel": row.is_entry_level,
            "seasons": seasons,
        }

    def team_contracts(self, team_id: int, season: int) -> TeamContractsResponseData:
        self.require_season(season)
        team = self.team_summary(team_id)
        ids = self.repository.contract_players(team_id, season)
        rows: list[TeamContractRowData] = []
        for player_id in ids:
            contract = self.contract(player_id, season)
            if contract is not None:
                contract_season = next(
                    (
                        s
                        for s in contract["seasons"]
                        if s["season"] == season
                        and s["owningTeam"] is not None
                        and (s["owningTeam"]["id"] == team_id)
                    ),
                    None,
                )
                if contract_season is not None:
                    rows.append(
                        {
                            "player": self.player_identity(player_id),
                            "contract": contract,
                            "season": contract_season,
                        }
                    )
        return {"team": team, "season": season, "contracts": rows}

    def team_cap(self, team_id: int, season: int) -> TeamCapData:
        self.require_season(season)
        self.team_summary(team_id)
        row = self.repository.cap(team_id, season, buried_relief_cents(season))
        if row is None:
            raise CapUnavailable(season=season)
        ceiling = row.salary_cap_cents
        return {
            "teamId": team_id,
            "season": season,
            "salaryCapCents": ceiling,
            "activeRosterCapCents": row.active_cap,
            "ltirCapCents": row.ltir_cap,
            "minorsCapCents": row.minors_cap,
            "totalCommitmentsCents": row.total_cap,
            "capSpaceCents": ceiling - row.active_cap if ceiling is not None else None,
            "calculationStatus": "ESTIMATE",
        }

    def search(
        self, query: str, types: Iterable[str], limit: int
    ) -> SearchResponseData:
        requested = set(types)
        players = (
            [
                self.player_identity(player_id)
                for player_id in self.repository.search_players(query, limit)
            ]
            if "player" in requested
            else []
        )
        teams = (
            list(map(team_data, self.repository.search_teams(query, limit)))
            if "team" in requested
            else []
        )
        return {"players": players, "teams": teams}

    def overview(self, season: int) -> OverviewResponseData:
        self.require_season(season)
        rows = self.repository.overview(season)
        summaries = [summary_data(r) for r in rows]
        skaters = [s for s in summaries if s["primaryPosition"] != "G"]
        values = [s["hockeyValue"] for s in skaters if s["hockeyValue"] is not None]
        return {
            "season": season,
            "league": {
                "players": len(summaries),
                "goals": sum((s["goals"] for s in skaters if s["goals"] is not None)),
                "gamesPlayed": sum(
                    (
                        s["gamesPlayed"]
                        for s in summaries
                        if s["gamesPlayed"] is not None
                    )
                ),
                "averageHockeyValue": sum(values) / len(values)
                if len(values) > 0
                else None,
            },
            "leaders": {
                "hockeyValue": top_summaries(skaters, "hockeyValue"),
                "points": top_summaries(skaters, "points"),
                "goals": top_summaries(skaters, "goals"),
                "gameScorePer60": top_summaries(skaters, "gameScorePer60"),
            },
        }

    def compare(self, ids: list[int], season: int) -> CompareResponseData:
        self.require_season(season)
        return {
            "season": season,
            "players": [
                {
                    "player": self.player_identity(player_id),
                    "stats": self.player_stats(player_id, season),
                    "value": self.hockey_value(player_id, season),
                    "contract": self.contract(player_id, season),
                }
                for player_id in ids
            ],
        }

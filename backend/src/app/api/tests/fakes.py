"""In-memory read repository for API behavior tests."""

from app.api.service import TradeValueService

from dataclasses import dataclass, field
from collections.abc import Mapping
from operator import attrgetter
from app.api.domain import (
    CapRow,
    ContractRow,
    ContractSeasonRow,
    GoalieRow,
    IdentityRow,
    PlayerPage,
    PlayerQuery,
    SeasonRow,
    SummaryRow,
    TeamRow,
)
from fastapi.testclient import TestClient
from typing import Literal


type ServiceMode = Literal["present", "empty", "absent", "null-ceiling"]


@dataclass(slots=True, kw_only=True, frozen=True)
class ServiceScenario:
    service: TradeValueService
    mode: ServiceMode


@dataclass(slots=True, kw_only=True, frozen=True)
class MemoryApiRepository:
    health_failure: Exception | None = None
    health_checks: list[bool] = field(default_factory=list)
    season_rows: tuple[SeasonRow, ...] = ()
    player_rows: tuple[IdentityRow, ...] = ()
    team_rows: tuple[TeamRow, ...] = ()
    summaries: tuple[SummaryRow, ...] = ()
    goalie_rows: tuple[tuple[int, int, GoalieRow], ...] = ()
    contract_rows: tuple[ContractRow, ...] = ()
    contract_season_rows: tuple[tuple[int, ContractSeasonRow], ...] = ()
    cap_rows: tuple[tuple[int, int, CapRow], ...] = ()
    contract_player_rows: tuple[tuple[int, int, int], ...] | None = None
    missing_history: tuple[int, ...] = ()

    def check_health(self) -> None:
        self.health_checks.append(True)
        if self.health_failure is not None:
            raise self.health_failure

    def current_season(self, latest: int) -> int | None:
        return max(
            (r.start_year for r in self.season_rows if r.start_year <= latest),
            default=None,
        )

    def has_season(self, season: int, latest: int) -> bool:
        return season <= latest and any(
            r.start_year == season for r in self.season_rows
        )

    def seasons(self, latest: int) -> tuple[SeasonRow, ...]:
        return tuple(r for r in self.season_rows if r.start_year <= latest)

    def player(self, player_id: int) -> IdentityRow | None:
        return next((r for r in self.player_rows if r.id == player_id), None)

    def team(self, team_id: int) -> TeamRow | None:
        return next((r for r in self.team_rows if r.id == team_id), None)

    def players(self, query: PlayerQuery) -> PlayerPage:
        rows = tuple(
            r
            for r in self.summaries
            if r.season == query.season
            and (query.team is None or r.abbreviation == query.team.upper())
            and (query.position is None or r.primary_position == query.position)
            and (query.roster_status is None or r.roster_status == query.roster_status)
            and (
                query.search is None
                or query.search.strip().casefold() in r.full_name.casefold()
            )
        )
        start = (query.page - 1) * query.page_size
        return PlayerPage(rows=rows[start : start + query.page_size], total=len(rows))

    def teams(self) -> tuple[TeamRow, ...]:
        return tuple(r for r in self.team_rows if r.team_active)

    def roster_counts(self, team_id: int) -> Mapping[str, int]:
        return {
            status: sum(
                r.team_id == team_id and r.roster_status == status
                for r in self.player_rows
            )
            for status in ("ACTIVE", "MINORS", "LTIR", "UNKNOWN")
        }

    def roster(
        self, team_id: int, season: int, status: str | None
    ) -> tuple[SummaryRow, ...]:
        rows = (
            r
            for r in self.summaries
            if r.team_id == team_id
            and r.season == season
            and (status is None or r.roster_status == status)
        )
        return tuple(sorted(rows, key=attrgetter("full_name", "id")))[:100]

    def summary_for_player(self, player_id: int, season: int) -> SummaryRow | None:
        return next(
            (r for r in self.summaries if r.id == player_id and r.season == season),
            None,
        )

    def goalie(self, player_id: int, season: int) -> GoalieRow | None:
        return next(
            (
                r
                for pid, year, r in self.goalie_rows
                if pid == player_id and year == season
            ),
            None,
        )

    def player_seasons(self, player_id: int) -> tuple[int, ...]:
        return tuple(
            sorted(
                {r.season for r in self.summaries if r.id == player_id}
                | set(self.missing_history),
                reverse=True,
            )
        )[:40]

    def leaders(
        self, season: int, position: str | None, team: str | None, limit: int
    ) -> tuple[SummaryRow, ...]:
        return tuple(
            r
            for r in self.summaries
            if r.season == season
            and r.hockey_value is not None
            and (position is None or r.primary_position == position)
            and (team is None or r.abbreviation == team.upper())
        )[:limit]

    def contract(self, player_id: int, current_season: int) -> ContractRow | None:
        return next((r for r in self.contract_rows if r.player_id == player_id), None)

    def contract_seasons(self, contract_id: int) -> tuple[ContractSeasonRow, ...]:
        return tuple(r for cid, r in self.contract_season_rows if cid == contract_id)

    def contract_players(self, team_id: int, season: int) -> tuple[int, ...]:
        if self.contract_player_rows is not None:
            return tuple(
                pid
                for tid, year, pid in self.contract_player_rows
                if tid == team_id and year == season
            )
        ids = {
            cid
            for cid, r in self.contract_season_rows
            if r.team_id == team_id and r.season_start_year == season
        }
        return tuple(r.player_id for r in self.contract_rows if r.id in ids)

    def cap(self, team_id: int, season: int, relief: int) -> CapRow | None:
        return next(
            (r for tid, year, r in self.cap_rows if tid == team_id and year == season),
            None,
        )

    def search_players(self, query: str, limit: int) -> tuple[int, ...]:
        return tuple(
            r.id for r in self.player_rows if query.casefold() in r.full_name.casefold()
        )[:limit]

    def search_teams(self, query: str, limit: int) -> tuple[TeamRow, ...]:
        return tuple(
            r for r in self.team_rows if query.casefold() in str(r.team_name).casefold()
        )[:limit]

    def overview(self, season: int) -> tuple[SummaryRow, ...]:
        return tuple(
            r
            for r in self.summaries
            if r.season == season and r.games_played is not None
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class HttpScenario:
    client: TestClient
    repository: MemoryApiRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class SeasonBoundaryScenario:
    before: TradeValueService
    on: TradeValueService

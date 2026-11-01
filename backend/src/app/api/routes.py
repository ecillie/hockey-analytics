"""FastAPI route definitions matching docs/api-contract.md."""

from collections.abc import Generator
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.api import schemas
from app.api.domain import PlayerQuery, PlayerSort, SortOrder
from app.api.errors import (
    DatabaseUnavailable,
    InvalidComparisonIds,
    InvalidComparisonSelection,
    InvalidSearchQuery,
    InvalidSearchTypes,
)
from app.api.repository import SqlApiRepository
from app.api.service import TradeValueService


def get_service(request: Request) -> Generator[TradeValueService, None, None]:
    resources = getattr(request.app.state, "database", None)
    if resources is None:
        raise DatabaseUnavailable()
    with resources.sessions() as session:
        yield TradeValueService(repository=SqlApiRepository(session=session))


type Service = Annotated[TradeValueService, Depends(get_service)]
type PlayerId = Annotated[int, Path(gt=0)]
type TeamId = Annotated[int, Path(gt=0)]
type Season = Annotated[int, Query(ge=1900, le=2200)]
type OptionalSeason = Annotated[int | None, Query(ge=1900, le=2200)]

type TeamFilter = Annotated[str | None, Query(min_length=2, max_length=4)]
type PlayerSearch = Annotated[str | None, Query(max_length=120)]
type PageNumber = Annotated[int, Query(ge=1)]
type PageSize = Annotated[int, Query(ge=1, le=100)]
type SearchQuery = Annotated[str, Query(min_length=2, max_length=120)]
type SearchLimit = Annotated[int, Query(ge=1, le=20)]


def create_router() -> APIRouter:
    router = APIRouter(
        prefix="/api",
        responses={
            400: {"model": schemas.ErrorResponse, "description": "Invalid request"},
            404: {"model": schemas.ErrorResponse, "description": "Resource not found"},
            500: {"model": schemas.ErrorResponse, "description": "Internal API error"},
            503: {
                "model": schemas.ErrorResponse,
                "description": "Database unavailable",
            },
        },
    )

    @router.get("/health", response_model=schemas.HealthResponse)
    def health(service: Service):
        service.check_health()
        return {"status": "ok"}

    @router.get("/seasons", response_model=schemas.SeasonInfo)
    def seasons(service: Service):
        return service.seasons()

    @router.get("/players", response_model=schemas.PaginatedPlayers)
    def players(
        service: Service,
        season: OptionalSeason = None,
        team: TeamFilter = None,
        position: schemas.Position | None = None,
        rosterStatus: schemas.RosterStatus | None = None,
        search: PlayerSearch = None,
        sort: PlayerSort = "hockeyValue",
        order: SortOrder = "desc",
        page: PageNumber = 1,
        pageSize: PageSize = 25,
    ):
        selected = season if season is not None else service.current_season()
        return service.players(
            PlayerQuery(
                season=selected,
                team=team,
                position=position.value if position is not None else None,
                roster_status=rosterStatus.value if rosterStatus is not None else None,
                search=search,
                sort=sort,
                order=order,
                page=page,
                page_size=pageSize,
            )
        )

    @router.get("/players/compare", response_model=schemas.CompareResponse)
    def compare_players(service: Service, ids: str, season: Season):
        try:
            player_ids = [
                int(value.strip()) for value in ids.split(",") if value.strip()
            ]
        except ValueError as exc:
            raise InvalidComparisonIds() from exc
        if (
            len(player_ids) < 2
            or len(player_ids) > 4
            or any(value <= 0 for value in player_ids)
            or len(set(player_ids)) != len(player_ids)
        ):
            raise InvalidComparisonSelection()
        return service.compare(player_ids, season)

    @router.get("/players/{player_id}", response_model=schemas.PlayerIdentity)
    def player(service: Service, player_id: PlayerId):
        return service.player_identity(player_id)

    @router.get("/players/{player_id}/stats", response_model=schemas.PlayerStats)
    def player_stats(service: Service, player_id: PlayerId, season: Season):
        return service.player_stats(player_id, season)

    @router.get(
        "/players/{player_id}/seasons", response_model=list[schemas.SeasonHistoryRow]
    )
    def player_seasons(service: Service, player_id: PlayerId):
        return service.player_seasons(player_id)

    @router.get(
        "/players/{player_id}/value/history",
        response_model=list[schemas.HockeyValueHistoryPoint],
    )
    def value_history(service: Service, player_id: PlayerId):
        return service.value_history(player_id)

    @router.get("/players/{player_id}/value", response_model=schemas.HockeyValue)
    def hockey_value(
        service: Service, player_id: PlayerId, season: OptionalSeason = None
    ):
        return service.hockey_value(player_id, season)

    @router.get("/players/{player_id}/contract", response_model=schemas.Contract | None)
    def contract(service: Service, player_id: PlayerId):
        return service.contract(player_id)

    @router.get("/rankings/hockey-value", response_model=list[schemas.PlayerSummary])
    def hockey_value_leaders(
        service: Service,
        season: Season,
        position: schemas.Position | None = None,
        team: TeamFilter = None,
        limit: PageSize = 10,
    ):
        return service.leaders(
            season, position.value if position else None, team, limit
        )

    @router.get("/teams", response_model=list[schemas.TeamSummary])
    def teams(service: Service):
        return service.teams()

    @router.get("/teams/{team_id}", response_model=schemas.Team)
    def team(service: Service, team_id: TeamId):
        return service.team(team_id)

    @router.get("/teams/{team_id}/roster", response_model=schemas.TeamRosterResponse)
    def roster(
        service: Service,
        team_id: TeamId,
        season: Season,
        status: schemas.RosterStatus | None = None,
    ):
        return service.roster(team_id, season, status.value if status else None)

    @router.get(
        "/teams/{team_id}/contracts", response_model=schemas.TeamContractsResponse
    )
    def team_contracts(service: Service, team_id: TeamId, season: Season):
        return service.team_contracts(team_id, season)

    @router.get("/teams/{team_id}/cap", response_model=schemas.TeamCap)
    def team_cap(service: Service, team_id: TeamId, season: Season):
        return service.team_cap(team_id, season)

    @router.get("/search", response_model=schemas.SearchResponse)
    def search(
        service: Service,
        q: SearchQuery,
        types: str = "player,team",
        limit: SearchLimit = 8,
    ):
        q = q.strip()
        if len(q) < 2:
            raise InvalidSearchQuery()
        requested = [value.strip() for value in types.split(",") if value.strip()]
        invalid = sorted(set(requested) - {"player", "team"})
        if not requested or invalid:
            raise InvalidSearchTypes()
        return service.search(q, requested, limit)

    @router.get("/overview", response_model=schemas.OverviewResponse)
    def overview(service: Service, season: Season):
        return service.overview(season)

    return router

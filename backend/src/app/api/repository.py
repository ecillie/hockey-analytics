"""Typed persistence boundary for read-only API operations."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import TypeAdapter
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import queries
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
    SummarySelection,
    TeamRow,
)


@runtime_checkable
class ApiRepository(Protocol):
    def check_health(self) -> None: ...
    def current_season(self, latest: int) -> int | None: ...
    def has_season(self, season: int, latest: int) -> bool: ...
    def seasons(self, latest: int) -> tuple[SeasonRow, ...]: ...
    def player(self, player_id: int) -> IdentityRow | None: ...
    def team(self, team_id: int) -> TeamRow | None: ...
    def players(self, query: PlayerQuery) -> PlayerPage: ...
    def teams(self) -> tuple[TeamRow, ...]: ...
    def roster_counts(self, team_id: int) -> Mapping[str, int]: ...
    def roster(
        self, team_id: int, season: int, status: str | None
    ) -> tuple[SummaryRow, ...]: ...
    def summary_for_player(self, player_id: int, season: int) -> SummaryRow | None: ...
    def goalie(self, player_id: int, season: int) -> GoalieRow | None: ...
    def player_seasons(self, player_id: int) -> tuple[int, ...]: ...
    def leaders(
        self, season: int, position: str | None, team: str | None, limit: int
    ) -> tuple[SummaryRow, ...]: ...
    def contract(self, player_id: int, current_season: int) -> ContractRow | None: ...
    def contract_seasons(self, contract_id: int) -> tuple[ContractSeasonRow, ...]: ...
    def contract_players(self, team_id: int, season: int) -> tuple[int, ...]: ...
    def cap(self, team_id: int, season: int, relief: int) -> CapRow | None: ...
    def search_players(self, query: str, limit: int) -> tuple[int, ...]: ...
    def search_teams(self, query: str, limit: int) -> tuple[TeamRow, ...]: ...
    def overview(self, season: int) -> tuple[SummaryRow, ...]: ...


def read_one[T](
    session: Session, sql: str, params: Mapping[str, object], row_type: type[T]
) -> T | None:
    row = session.execute(text(sql), params).mappings().first()
    return None if row is None else TypeAdapter(row_type).validate_python(dict(row))


def read_all[T](
    session: Session, sql: str, params: Mapping[str, object], row_type: type[T]
) -> tuple[T, ...]:
    rows = session.execute(text(sql), params).mappings()
    adapter = TypeAdapter(row_type)
    return tuple(adapter.validate_python(dict(row)) for row in rows)


def select_summary_rows(
    session: Session, selection: SummarySelection
) -> tuple[SummaryRow, ...]:
    query = (
        queries.SUMMARY_CTES
        + f" SELECT * FROM summary WHERE {selection.where} ORDER BY {selection.order}"
    )
    bind = {"season": selection.season, **dict(selection.bindings)}
    if selection.limit is not None:
        query += " LIMIT :_limit"
        bind["_limit"] = selection.limit
    if selection.offset is not None:
        query += " OFFSET :_offset"
        bind["_offset"] = selection.offset
    return read_all(session, query, bind, SummaryRow)


@dataclass(slots=True, kw_only=True, frozen=True)
class SqlApiRepository:
    session: Session

    def check_health(self) -> None:
        self.session.execute(text("SELECT 1"))

    def current_season(self, latest: int) -> int | None:
        return self.session.execute(
            text(queries.CURRENT_SEASON_SQL), {"latest_started_season": latest}
        ).scalar_one_or_none()

    def has_season(self, season: int, latest: int) -> bool:
        return self.session.execute(
            text(queries.HAS_SEASON_SQL),
            {"season": season, "latest_started_season": latest},
        ).scalar_one()

    def seasons(self, latest: int) -> tuple[SeasonRow, ...]:
        return read_all(
            self.session,
            queries.SEASONS_SQL,
            {"latest_started_season": latest},
            SeasonRow,
        )

    def player(self, player_id: int) -> IdentityRow | None:
        return read_one(
            self.session,
            queries.PLAYER_IDENTITY_SQL,
            {"player_id": player_id},
            IdentityRow,
        )

    def team(self, team_id: int) -> TeamRow | None:
        return read_one(self.session, queries.TEAM_SQL, {"team_id": team_id}, TeamRow)

    def players(self, query: PlayerQuery) -> PlayerPage:
        clauses = [
            "(games_played IS NOT NULL OR team_id IS NOT NULL OR cap_hit_cents IS NOT NULL)"
        ]
        params: dict[str, str | int] = {}
        if query.team is not None:
            clauses.append("UPPER(abbreviation) = UPPER(:team)")
            params["team"] = query.team
        if query.position is not None:
            clauses.append("primary_position = :position")
            params["position"] = query.position
        if query.roster_status is not None:
            clauses.append("roster_status = :roster_status")
            params["roster_status"] = query.roster_status
        if query.search is not None and query.search != "":
            clauses.append("full_name ILIKE :search")
            params["search"] = f"%{query.search.strip()}%"
        where = " AND ".join(clauses)
        count_sql = (
            queries.SUMMARY_CTES + f" SELECT COUNT(*) FROM summary WHERE {where}"
        )
        total = self.session.execute(
            text(count_sql), {"season": query.season, **params}
        ).scalar_one()
        columns = {
            "name": "full_name",
            "team": "abbreviation",
            "gamesPlayed": "games_played",
            "goals": "goals",
            "assists": "assists",
            "points": "points",
            "gameScore": "game_score",
            "gameScorePer60": "game_score_per_60",
            "hockeyValue": "hockey_value",
            "capHitCents": "cap_hit_cents",
        }
        column = columns[query.sort]
        direction = "ASC" if query.order == "asc" else "DESC"
        rows = select_summary_rows(
            self.session,
            SummarySelection(
                season=query.season,
                where=where,
                bindings=tuple(params.items()),
                order=f"{column} {direction} NULLS LAST, id ASC",
                limit=query.page_size,
                offset=(query.page - 1) * query.page_size,
            ),
        )
        return PlayerPage(rows=rows, total=total)

    def teams(self) -> tuple[TeamRow, ...]:
        return read_all(self.session, queries.TEAMS_SQL, {}, TeamRow)

    def roster_counts(self, team_id: int) -> Mapping[str, int]:
        rows = self.session.execute(
            text(queries.ROSTER_COUNTS_SQL), {"team_id": team_id}
        ).mappings()
        return {row["roster_status"]: row["count"] for row in rows}

    def roster(
        self, team_id: int, season: int, status: str | None
    ) -> tuple[SummaryRow, ...]:
        where = "team_id = :team_id"
        params: dict[str, str | int] = {"team_id": team_id}
        if status is not None:
            where += " AND roster_status = :status"
            params["status"] = status
        return select_summary_rows(
            self.session,
            SummarySelection(
                season=season,
                where=where,
                bindings=tuple(params.items()),
                order="full_name ASC, id ASC",
                limit=100,
            ),
        )

    def summary_for_player(self, player_id: int, season: int) -> SummaryRow | None:
        rows = select_summary_rows(
            self.session,
            SummarySelection(
                season=season,
                where="id = :player_id",
                bindings=(("player_id", player_id),),
            ),
        )
        return next(iter(rows), None)

    def goalie(self, player_id: int, season: int) -> GoalieRow | None:
        return read_one(
            self.session,
            queries.GOALIE_SQL,
            {"player_id": player_id, "season": season},
            GoalieRow,
        )

    def player_seasons(self, player_id: int) -> tuple[int, ...]:
        rows = self.session.execute(
            text(queries.PLAYER_SEASONS_SQL), {"player_id": player_id}
        ).scalars()
        return tuple(rows)

    def leaders(
        self, season: int, position: str | None, team: str | None, limit: int
    ) -> tuple[SummaryRow, ...]:
        clauses = ["hockey_value IS NOT NULL"]
        params: dict[str, str | int] = {}
        if position is not None:
            clauses.append("primary_position=:position")
            params["position"] = position
        if team is not None:
            clauses.append("UPPER(abbreviation)=UPPER(:team)")
            params["team"] = team
        return select_summary_rows(
            self.session,
            SummarySelection(
                season=season,
                where=" AND ".join(clauses),
                bindings=tuple(params.items()),
                order="hockey_value DESC NULLS LAST, id ASC",
                limit=limit,
            ),
        )

    def contract(self, player_id: int, current_season: int) -> ContractRow | None:
        return read_one(
            self.session,
            queries.CONTRACT_SQL,
            {"player_id": player_id, "current_season": current_season},
            ContractRow,
        )

    def contract_seasons(self, contract_id: int) -> tuple[ContractSeasonRow, ...]:
        return read_all(
            self.session,
            queries.CONTRACT_SEASONS_SQL,
            {"contract_id": contract_id},
            ContractSeasonRow,
        )

    def contract_players(self, team_id: int, season: int) -> tuple[int, ...]:
        return tuple(
            self.session.execute(
                text(queries.CONTRACT_PLAYERS_SQL),
                {"team_id": team_id, "season": season},
            ).scalars()
        )

    def cap(self, team_id: int, season: int, relief: int) -> CapRow | None:
        return read_one(
            self.session,
            queries.CAP_SQL,
            {"team_id": team_id, "season": season, "buried_relief_cents": relief},
            CapRow,
        )

    def search_players(self, query: str, limit: int) -> tuple[int, ...]:
        return tuple(
            self.session.execute(
                text(queries.SEARCH_PLAYERS_SQL),
                {"q": f"%{query.strip()}%", "limit": limit},
            ).scalars()
        )

    def search_teams(self, query: str, limit: int) -> tuple[TeamRow, ...]:
        return read_all(
            self.session,
            queries.SEARCH_TEAMS_SQL,
            {"q": f"%{query.strip()}%", "limit": limit},
            TeamRow,
        )

    def overview(self, season: int) -> tuple[SummaryRow, ...]:
        return select_summary_rows(
            self.session,
            SummarySelection(season=season, where="games_played IS NOT NULL"),
        )

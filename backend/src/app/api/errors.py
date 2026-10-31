"""Typed API failures preserving the public error envelope."""


class ApiProblem(Exception):
    def __init__(
        self,
        *,
        status: int,
        code: str,
        message: str,
        details: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


class SeasonsUnavailable(ApiProblem):
    def __init__(self) -> None:
        super().__init__(
            status=503, code="SEASONS_UNAVAILABLE", message="No seasons are configured."
        )


class InvalidSeason(ApiProblem):
    def __init__(self, *, season: int) -> None:
        self.season = season
        super().__init__(
            status=400,
            code="INVALID_SEASON",
            message="The requested season is not available.",
            details={"season": ["Unknown season."]},
        )


class PlayerNotFound(ApiProblem):
    def __init__(self, *, player_id: int) -> None:
        self.player_id = player_id
        super().__init__(
            status=404, code="PLAYER_NOT_FOUND", message="Player not found."
        )


class TeamNotFound(ApiProblem):
    def __init__(self, *, team_id: int) -> None:
        self.team_id = team_id
        super().__init__(status=404, code="TEAM_NOT_FOUND", message="Team not found.")


class CapUnavailable(ApiProblem):
    def __init__(self, *, season: int) -> None:
        self.season = season
        super().__init__(
            status=503,
            code="SEASONS_UNAVAILABLE",
            message="Season cap data is unavailable.",
        )


class DatabaseUnavailable(ApiProblem):
    def __init__(self) -> None:
        super().__init__(
            status=503,
            code="DATABASE_UNAVAILABLE",
            message="The data service is temporarily unavailable.",
        )


class InvalidComparisonIds(ApiProblem):
    def __init__(self) -> None:
        super().__init__(
            status=400,
            code="INVALID_COMPARISON",
            message="Player IDs must be integers.",
            details={"ids": ["Use comma-separated integer IDs."]},
        )


class InvalidComparisonSelection(ApiProblem):
    def __init__(self) -> None:
        super().__init__(
            status=400,
            code="INVALID_COMPARISON",
            message="Select between 2 and 4 distinct players.",
            details={"ids": ["Use 2 to 4 distinct positive IDs."]},
        )


class InvalidSearchQuery(ApiProblem):
    def __init__(self) -> None:
        super().__init__(
            status=400,
            code="INVALID_REQUEST",
            message="The request parameters are invalid.",
            details={
                "q": [
                    "Search queries must contain at least two non-whitespace characters."
                ]
            },
        )


class InvalidSearchTypes(ApiProblem):
    def __init__(self) -> None:
        super().__init__(
            status=400,
            code="INVALID_SEARCH_TYPES",
            message="Search types must be player or team.",
            details={"types": ["Use player, team, or both."]},
        )

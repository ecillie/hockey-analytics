"""Shared HTTP smoke payload checks and structured operational failures."""


def valid_health(body: object) -> bool:
    return body == {"status": "ok"}


def valid_seasons(body: object) -> bool:
    return (
        isinstance(body, dict)
        and bool(body.get("availableSeasons"))
        and isinstance(body.get("currentSeason"), int)
    )


class SmokeResponseError(RuntimeError):
    def __init__(self, *, operation: str, path: str, status: int, body: str) -> None:
        super().__init__(
            f"{operation} smoke check failed for {path}: status={status} body={body}"
        )
        self.operation = operation
        self.path = path
        self.status = status
        self.body = body


class ContainerReadinessError(RuntimeError):
    def __init__(self, *, attempts: int, failure: Exception) -> None:
        super().__init__(
            f"container did not become healthy after {attempts} attempts: {failure}"
        )
        self.attempts = attempts
        self.failure = failure


class ReferenceDataError(RuntimeError):
    def __init__(self, *, sources: list[str], seasons: int) -> None:
        super().__init__(
            f"initial reference data is incomplete: sources={sources} seasons={seasons}"
        )
        self.sources = tuple(sources)
        self.seasons = seasons

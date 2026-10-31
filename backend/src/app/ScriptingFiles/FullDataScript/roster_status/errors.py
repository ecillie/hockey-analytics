"""Typed roster transport and feed failures."""


class InvalidJsonResponseError(ValueError):
    def __init__(self, *, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Invalid JSON/JSONP response: {reason}")


class FeedFetchError(RuntimeError):
    def __init__(self, *, source: str, reason: str) -> None:
        self.source = source
        self.reason = reason
        super().__init__(f"Unable to fetch {source}: {reason}")


class IncompleteRosterFeedError(RuntimeError):
    def __init__(self, *, errors: tuple[str, ...]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))

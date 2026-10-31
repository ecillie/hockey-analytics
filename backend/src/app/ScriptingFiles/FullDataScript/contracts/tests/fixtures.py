"""Immutable saved-response clients for contract source tests."""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(slots=True, kw_only=True, frozen=True)
class SavedResponse:
    status_code: int
    headers: Mapping[str, str]
    text: str
    url: str


@dataclass(slots=True, kw_only=True, frozen=True)
class SavedSession:
    response: SavedResponse

    def get(self, url: str, *, timeout: float) -> SavedResponse:
        return self.response

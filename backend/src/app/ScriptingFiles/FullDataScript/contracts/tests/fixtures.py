"""Immutable saved-response clients for contract source tests."""

from collections.abc import Mapping
from dataclasses import dataclass

import requests


@dataclass(slots=True, kw_only=True, frozen=True)
class SavedResponse:
    status_code: int
    headers: Mapping[str, str]
    text: str
    url: str

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


@dataclass(slots=True, kw_only=True, frozen=True)
class SavedSession:
    response: SavedResponse

    def get(self, url: str, *, timeout: float) -> SavedResponse:
        return self.response

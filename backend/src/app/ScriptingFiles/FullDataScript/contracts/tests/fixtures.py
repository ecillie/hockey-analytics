"""Immutable saved-response clients for contract source tests."""

from collections.abc import Mapping
from dataclasses import dataclass
import requests
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text


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


def read_contract_fixture(name: str) -> str:
    return (
        Path(__file__)
        .resolve()
        .parents[7]
        .joinpath("tests", "backend", "fixtures", "ingestion", name)
    ).read_text(encoding="utf-8")


@pytest.fixture()
def database(disposable_database_url):
    engine = create_engine(disposable_database_url)
    with engine.begin() as connection:
        if (
            connection.execute(
                text("SELECT to_regclass('public.players')")
            ).scalar_one()
            is None
        ):
            raise pytest.skip.Exception("the disposable database has not been migrated")
        if (
            connection.execute(
                text("SELECT to_regclass('public.source_records')")
            ).scalar_one()
            is None
        ):
            raise pytest.skip.Exception("the disposable database has not been migrated")
        has_capspace = connection.execute(
            text("SELECT count(*) FROM data_sources WHERE code='capspace'")
        ).scalar_one()
        if not has_capspace:
            raise pytest.skip.Exception(
                "the disposable database has not been upgraded to the CapSpace migration"
            )
        connection.execute(
            text("TRUNCATE teams, players, ingestion_runs RESTART IDENTITY CASCADE")
        )

    yield engine
    engine.dispose()

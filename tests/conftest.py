"""Test selection and external-resource isolation."""

from collections.abc import Generator
import os
import socket

import pytest
import sklearn
from sqlalchemy.engine import make_url


def pytest_report_header() -> str:
    return f"scikit-learn {sklearn.__version__} initialized before collection"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if (
            "disposable_database_url" in getattr(item, "fixturenames", ())
            and item.get_closest_marker("integration") is None
        ):
            raise pytest.UsageError(
                f"database test must be marked integration: {item.nodeid}"
            )
        if item.get_closest_marker("integration") is None:
            item.add_marker(pytest.mark.unit)


def reject_network_access(*args: object, **kwargs: object) -> None:
    raise AssertionError("unit tests must use a saved response or behavioral fake")


@pytest.fixture(autouse=True)
def isolate_unit_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    if request.node.get_closest_marker("unit") is not None:
        monkeypatch.setattr(socket.socket, "connect", reject_network_access)
        monkeypatch.setattr(socket.socket, "connect_ex", reject_network_access)


@pytest.fixture(scope="session", autouse=True)
def isolate_integration_database() -> Generator[None]:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        yield
        return
    database = make_url(database_url).database
    if database is None or not database.startswith("tradevalue_test"):
        raise pytest.UsageError(
            "TEST_DATABASE_URL must name a disposable tradevalue_test database"
        )
    with pytest.MonkeyPatch.context() as environment:
        environment.setenv("ENV", "dev")
        environment.setenv("TRADEVALUE_ENV_FILE", os.devnull)
        environment.setenv("DEV_DATABASE_URL", database_url)
        environment.setenv("DATABASE_URL", database_url)
        yield


@pytest.fixture(scope="session")
def disposable_database_url() -> str:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        raise pytest.skip.Exception(
            "integration tests require a disposable TEST_DATABASE_URL"
        )
    database = make_url(database_url).database
    if database is None or not database.startswith("tradevalue_test"):
        raise pytest.UsageError(
            "TEST_DATABASE_URL must name a disposable tradevalue_test database"
        )
    return database_url

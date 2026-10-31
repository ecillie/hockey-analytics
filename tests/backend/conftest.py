"""Explicit fixture plugins for backend concept tests."""

from collections.abc import Generator
import os

import pytest
from sqlalchemy.engine import make_url

pytest_plugins = (
    "app.ScriptingFiles.FullDataScript.roster_status.tests.fixtures",
    "app.ScriptingFiles.FullDataScript.source_ingestion.tests.fixtures",
    "app.ScriptingFiles.FullDataScript.contracts.tests.fixtures",
)


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

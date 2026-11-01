"""Repository migration loading and subprocess verification."""

import importlib.util
import os
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from app.config import AppEnvironment, DatabaseSettings
from app.database import open_database_resources
from app.shared.cleanup import complete_cleanup


@dataclass(slots=True, kw_only=True, frozen=True)
class MigrationDatabase:
    admin: Engine
    name: str

    @property
    def quoted_name(self) -> str:
        return self.admin.dialect.identifier_preparer.quote(self.name)

    def create_database(self) -> None:
        with self.admin.connect() as connection:
            connection.execute(text(f"CREATE DATABASE {self.quoted_name}"))

    def drop_database(self) -> None:
        with self.admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": self.name},
            )
            connection.execute(text(f"DROP DATABASE IF EXISTS {self.quoted_name}"))


@contextmanager
def open_migration_database(source_url: str) -> Generator[str]:
    url = make_url(source_url)
    name = f"tradevalue_migration_{uuid4().hex[:12]}"
    settings = DatabaseSettings(
        environment=AppEnvironment.DEV,
        database_url=url.set(database="postgres").render_as_string(hide_password=False),
    )
    with open_database_resources(settings) as resources:
        database = MigrationDatabase(
            admin=resources.engine.execution_options(isolation_level="AUTOCOMMIT"),
            name=name,
        )
        primary: BaseException | None = None
        try:
            database.create_database()
            yield url.set(database=name).render_as_string(hide_password=False)
        except BaseException as failure:
            primary = failure
            raise
        finally:
            complete_cleanup((database.drop_database,), primary)


def load_initial_revision():
    spec = importlib.util.spec_from_file_location(
        "tradevalue_initial_revision", INITIAL_REVISION
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_command(database_url: str, *arguments: str, success=True):
    environment = {
        **os.environ,
        "DATABASE_URL": database_url,
        "DEV_DATABASE_URL": database_url,
        "TEST_DATABASE_URL": database_url,
        "ENV": "dev",
    }
    result = subprocess.run(
        [sys.executable, *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if success and result.returncode != 0:
        raise pytest.fail.Exception(
            f"command failed: {arguments}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    if not success and result.returncode == 0:
        raise pytest.fail.Exception(f"command unexpectedly passed: {arguments}")
    return result


ROOT = Path(__file__).parents[5]
INITIAL_REVISION = ROOT.joinpath(
    "backend", "migrations", "versions", "20260910_0001_initial_schema.py"
)

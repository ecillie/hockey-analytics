"""Owned resource probes for cleanup failure and ordering scenarios."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Self
from io import BytesIO
from urllib.error import HTTPError
from app.config import DatabaseSettings
from collections.abc import Generator
from contextlib import contextmanager
from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from app.api.routes import get_service
from app.api.repository import SqlApiRepository
from app.api.service import TradeValueService
from app.main import create_app
from app.shared.cleanup import complete_cleanup
from app.database import (
    DatabaseResources,
    open_database_cursor,
    open_database_transaction,
)
from psycopg2 import sql


@dataclass(slots=True, kw_only=True, frozen=True)
class CursorProbe:
    row: tuple[int, ...]
    failures: Mapping[str, BaseException]
    events: list[str]

    def __enter__(self) -> Self:
        return self

    def __exit__(self, kind: object, failure: object, traceback: object) -> None:
        self.close()

    def execute(self, query: object, parameters: object = None) -> None:
        self.events.append("execute")
        if (failure := self.failures.get("execute")) is not None:
            raise failure

    def fetchone(self) -> tuple[int, ...]:
        self.events.append("fetchone")
        if (failure := self.failures.get("fetchone")) is not None:
            raise failure
        return self.row

    def executemany(self, query: object, parameters: object) -> None:
        self.execute(query, parameters)

    def close(self) -> None:
        self.events.append("cursor.close")
        if (failure := self.failures.get("cursor.close")) is not None:
            raise failure


@dataclass(slots=True, kw_only=True, frozen=True)
class ResourceProbe:
    failures: Mapping[str, BaseException]
    events: list[str] = field(default_factory=list)
    cursor_resource: CursorProbe | None = None

    def cursor(self) -> CursorProbe:
        self.record_operation("cursor")
        assert self.cursor_resource is not None
        return self.cursor_resource

    def record_operation(self, name: str) -> None:
        self.events.append(name)
        if (failure := self.failures.get(name)) is not None:
            raise failure

    def commit(self) -> None:
        self.record_operation("commit")

    def rollback(self) -> None:
        self.record_operation("rollback")

    def close(self) -> None:
        self.record_operation("close")

    def dispose(self) -> None:
        self.record_operation("dispose")

    def create_resource(self, *args: object, **kwargs: object) -> Self:
        return self

    def create_sessions(self, *args: object, **kwargs: object) -> Self:
        self.record_operation("sessions")
        return self


@dataclass(slots=True, kw_only=True, frozen=True)
class ResourceFailureScenario:
    probe: ResourceProbe
    primary: BaseException | None
    expected: BaseException
    cause: Exception
    settings: DatabaseSettings


@dataclass(slots=True, kw_only=True, frozen=True)
class RepairFailureScenario:
    probe: ResourceProbe
    primary: BaseException | None
    expected: BaseException
    cause: Exception


@dataclass(slots=True, kw_only=True, frozen=True)
class CursorFailureScenario:
    connection: ResourceProbe
    primary: BaseException | None
    cleanup: BaseException | None
    cause: ValueError

    @property
    def expected_failure(self) -> BaseException | None:
        return self.primary if self.primary is not None else self.cleanup


@dataclass(slots=True, kw_only=True, frozen=True)
class HttpErrorScenario:
    body: BytesIO
    response: HTTPError
    primary: BaseException | None
    close_failure: BaseException | None
    events: list[str]

    @property
    def expected_failure(self) -> BaseException | None:
        return self.primary if self.primary is not None else self.close_failure


@dataclass(slots=True, kw_only=True, frozen=True)
class ResourceScenario:
    resources: DatabaseResources
    disposed: list[bool] = field(default_factory=list)

    def record_disposal(self, engine) -> None:
        self.disposed.append(True)

    def create_resources(self, settings: DatabaseSettings) -> DatabaseResources:
        return self.resources


@dataclass(slots=True, kw_only=True, frozen=True)
class RequestSessionScenario:
    session: Session
    dependency: Generator[TradeValueService]


@contextmanager
def open_sqlite_engine() -> Generator[Engine]:
    engine = create_engine("sqlite://")
    primary: BaseException | None = None
    try:
        yield engine
    except BaseException as failure:
        primary = failure
        raise
    finally:
        complete_cleanup((engine.dispose,), primary)


@contextmanager
def open_request_session(
    resources: DatabaseResources,
) -> Generator[RequestSessionScenario]:
    application = create_app()
    application.state.database = resources
    request = Request({"type": "http", "app": application})
    dependency = get_service(request)
    primary: BaseException | None = None
    try:
        service = next(dependency)
        service.check_health()
        assert isinstance(service.repository, SqlApiRepository)
        yield RequestSessionScenario(
            session=service.repository.session, dependency=dependency
        )
    except BaseException as failure:
        primary = failure
        raise
    finally:
        complete_cleanup((dependency.close,), primary)


@dataclass(slots=True, kw_only=True, frozen=True)
class ConfigurationScenario:
    name: str
    values: dict[str, str]


@dataclass(slots=True, kw_only=True, frozen=True)
class EnvironmentObservation:
    user: str
    host: str
    preserved: bool


@dataclass(slots=True, kw_only=True, frozen=True)
class TransactionScenario:
    settings: DatabaseSettings
    table: str

    def insert_row(self, connection) -> None:
        with open_database_cursor(connection) as cursor:
            cursor.execute(
                sql.SQL("INSERT INTO {} VALUES (1)").format(sql.Identifier(self.table))
            )

    def count_rows(self) -> int:
        with (
            open_database_transaction(self.settings) as connection,
            open_database_cursor(connection) as cursor,
        ):
            cursor.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(self.table))
            )
            row = cursor.fetchone()
            assert row is not None
            return row[0]

"""Owned resource probes for cleanup failure and ordering scenarios."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Self
from io import BytesIO
from urllib.error import HTTPError
from app.config import DatabaseSettings
from collections.abc import Generator
from sqlalchemy.orm import Session
from app.api.service import TradeValueService
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

    def execute(self, query: object, parameters: object = None) -> None:
        self.events.append("execute")
        if (failure := self.failures.get("execute")) is not None:
            raise failure

    def fetchone(self) -> tuple[int, ...]:
        self.events.append("fetchone")
        if (failure := self.failures.get("fetchone")) is not None:
            raise failure
        return self.row

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

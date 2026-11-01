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
from app.database import DatabaseResources
import psycopg2
from psycopg2 import sql


@dataclass(slots=True, kw_only=True, frozen=True)
class ResourceProbe:
    failures: Mapping[str, BaseException]
    events: list[str] = field(default_factory=list)

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
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("INSERT INTO {} VALUES (1)").format(sql.Identifier(self.table))
            )

    def count_rows(self) -> int:
        connection = psycopg2.connect(self.settings.database_url)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(
                        sql.Identifier(self.table)
                    )
                )
                row = cursor.fetchone()
                assert row is not None
                return row[0]
        finally:
            connection.close()

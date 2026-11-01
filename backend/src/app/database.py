"""Factories and scoped ownership for SQLAlchemy and DB-API resources."""

from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import psycopg2
from psycopg2.extensions import connection as PgConnection
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.shared.cleanup import complete_cleanup, retain_cleanup_failure
from app.shared.observability.domain import DiagnosticContext, TransactionOutcome
from app.shared.observability.services import report_transaction_outcome
from app.shared.errors import MissingDatabaseSchemaError
from app.config import DatabaseSettings, get_database_settings


@dataclass(slots=True, kw_only=True, frozen=True)
class DatabaseResources:
    engine: Engine
    sessions: sessionmaker[Session]


def create_database_resources(settings: DatabaseSettings) -> DatabaseResources:
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_recycle=settings.pool_recycle_seconds,
        pool_use_lifo=True,
        connect_args={"connect_timeout": settings.connect_timeout_seconds},
    )
    try:
        return DatabaseResources(
            engine=engine,
            sessions=sessionmaker(autocommit=False, autoflush=False, bind=engine),
        )
    except BaseException as failure:
        complete_cleanup((engine.dispose,), failure)
        raise


@contextmanager
def open_database_resources(settings: DatabaseSettings) -> Generator[DatabaseResources]:
    resources = create_database_resources(settings)
    primary: BaseException | None = None
    try:
        yield resources
    except BaseException as failure:
        primary = failure
        raise
    finally:
        complete_cleanup((resources.engine.dispose,), primary)


def init_db(settings: DatabaseSettings | None = None) -> None:
    selected = get_database_settings() if settings is None else settings
    with (
        open_database_resources(selected) as resources,
        resources.engine.connect() as connection,
    ):
        players_table = connection.execute(
            text("SELECT to_regclass('public.players')")
        ).scalar_one()
    if players_table is None:
        raise MissingDatabaseSchemaError(table="players")


def connect_database(settings: DatabaseSettings | None = None) -> PgConnection:
    selected = get_database_settings() if settings is None else settings
    return psycopg2.connect(
        selected.database_url, connect_timeout=selected.connect_timeout_seconds
    )


@contextmanager
def open_database_transaction(
    settings: DatabaseSettings | None = None,
    *,
    context: DiagnosticContext | None = None,
) -> Generator[PgConnection]:
    connection = connect_database(settings)
    primary: BaseException | None = None
    try:
        report_transaction_outcome(context, TransactionOutcome.STARTED)
        yield connection
        connection.commit()
        report_transaction_outcome(context, TransactionOutcome.COMMITTED)
    except BaseException as failure:
        primary = failure
        outcome = rollback_transaction(connection, primary)
        report_transaction_outcome(context, outcome, failure=primary)
        raise
    finally:
        complete_cleanup((connection.close,), primary)


def rollback_transaction(
    connection: PgConnection, primary: BaseException
) -> TransactionOutcome:
    try:
        connection.rollback()
    except BaseException as cleanup:
        retain_cleanup_failure(primary, cleanup)
        return TransactionOutcome.ROLLBACK_FAILED
    return TransactionOutcome.ROLLED_BACK


@runtime_checkable
class ContextualTransaction(Protocol):
    def __call__(
        self, *, context: DiagnosticContext | None = None
    ) -> AbstractContextManager[PgConnection]: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class DatabaseTransactionFactory:
    transaction: ContextualTransaction
    context: DiagnosticContext | None

    def __call__(self) -> AbstractContextManager[PgConnection]:
        return self.transaction(context=self.context)


database_resources = open_database_resources
database_transaction = open_database_transaction

"""Factories and scoped ownership for SQLAlchemy and DB-API resources."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

import psycopg2
from psycopg2.extensions import connection as PgConnection
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.shared.cleanup import complete_cleanup
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
def database_resources(settings: DatabaseSettings) -> Generator[DatabaseResources]:
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
        database_resources(selected) as resources,
        resources.engine.connect() as connection,
    ):
        players_table = connection.execute(
            text("SELECT to_regclass('public.players')")
        ).scalar_one()
    if players_table is None:
        raise RuntimeError("Database schema is missing; run Alembic upgrade head first")


def connect_database(settings: DatabaseSettings | None = None) -> PgConnection:
    selected = get_database_settings() if settings is None else settings
    return psycopg2.connect(
        selected.database_url, connect_timeout=selected.connect_timeout_seconds
    )


@contextmanager
def database_transaction(
    settings: DatabaseSettings | None = None,
) -> Generator[PgConnection]:
    connection = connect_database(settings)
    primary: BaseException | None = None
    try:
        yield connection
        connection.commit()
    except BaseException as failure:
        primary = failure
        complete_cleanup((connection.rollback,), primary)
        raise
    finally:
        complete_cleanup((connection.close,), primary)

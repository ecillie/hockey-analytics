"""Database connections for the API and ingestion scripts.

Alembic owns schema changes. This module does not call metadata.create_all() or
otherwise mutate the schema.
"""

from __future__ import annotations

from contextlib import contextmanager
import logging
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_database_settings
from app.observability import log_event

logger = logging.getLogger(__name__)


settings = get_database_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.pool_size,
    max_overflow=settings.max_overflow,
    pool_recycle=settings.pool_recycle_seconds,
    pool_use_lifo=True,
    hide_parameters=True,
    connect_args={"connect_timeout": settings.connect_timeout_seconds},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    """Verify that the migrated schema is reachable and present."""
    with engine.connect() as connection:
        players_table = connection.execute(
            text("SELECT to_regclass('public.players')")
        ).scalar_one()
    if players_table is None:
        raise RuntimeError(
            "Database schema is missing; run Alembic upgrade head first"
        )
    log_event(logger, "database.schema_checked", level=logging.DEBUG, environment=settings.environment.value)


def connect_database():
    """Return a psycopg2 connection for bulk loaders using DB-API directly."""
    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError(
            "Database access requires psycopg2-binary; "
            "run 'pip install -r backend/requirements.txt'"
        ) from exc

    try:
        connection = psycopg2.connect(
            settings.database_url,
            connect_timeout=settings.connect_timeout_seconds,
        )
    except Exception as exc:
        log_event(logger, "database.connection_failed", level=logging.ERROR, error=exc,
                  environment=settings.environment.value)
        raise
    log_event(logger, "database.connected", level=logging.DEBUG, environment=settings.environment.value)
    return connection


@contextmanager
def database_transaction() -> Iterator[object]:
    """Provide a DB-API connection that commits or rolls back atomically."""
    connection = connect_database()
    try:
        yield connection
        connection.commit()
        log_event(logger, "database.committed", level=logging.DEBUG, environment=settings.environment.value)
    except BaseException as exc:
        try:
            connection.rollback()
        except Exception as rollback_error:
            log_event(logger, "database.rollback_failed", level=logging.ERROR, error=rollback_error,
                      environment=settings.environment.value)
            raise
        log_event(logger, "database.rolled_back", level=logging.ERROR, error=exc,
                  environment=settings.environment.value)
        raise
    finally:
        connection.close()

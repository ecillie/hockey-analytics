"""Transaction-independent run records with scoped advisory-lock ownership."""

import hashlib
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from app.database import connect_database
from app.ScriptingFiles.FullDataScript.tracking.errors import (
    ConcurrentIngestionError,
    IngestionBatchError,
    UnknownIngestionSourceError,
)
from psycopg2.extensions import connection as PgConnection
from psycopg2.extensions import cursor as PgCursor
from psycopg2.extras import Json


def advisory_lock_key(job_name: str) -> int:
    raw = hashlib.sha256(f"tradevalue:{job_name}".encode()).digest()[:8]
    return int.from_bytes(raw, byteorder="big", signed=True)


def record_count(summary: Mapping[str, object]) -> int:
    dimensions = {"players", "teams", "cached", "profile_failures"}
    return sum(
        value
        for key, value in summary.items()
        if key not in dimensions and type(value) is int and value >= 0
    )


def summary_count(summary: Mapping[str, object], key: str, default: int = 0) -> int:
    value = summary.get(key, default)
    return value if isinstance(value, int) else default


@dataclass(slots=True, kw_only=True, frozen=True)
class PostgresIngestionRun:
    connection: PgConnection
    cursor: PgCursor
    run_id: int

    def succeed(self, summary: Mapping[str, object]) -> None:
        fallback = record_count(summary)
        self.cursor.execute(
            """UPDATE ingestion_runs SET status='succeeded',finished_at=CURRENT_TIMESTAMP,
                   records_read=%s,records_created=%s,records_updated=%s,
                   records_skipped=%s,metadata=%s WHERE id=%s""",
            (
                summary_count(summary, "records_read", fallback),
                summary_count(summary, "records_created"),
                summary_count(summary, "records_updated", fallback),
                summary_count(summary, "records_skipped"),
                Json(dict(summary)),
                self.run_id,
            ),
        )
        self.connection.commit()

    def fail(self, failure: BaseException) -> None:
        self.connection.rollback()
        if isinstance(failure, IngestionBatchError):
            progress = failure.committed_summary
            self.cursor.execute(
                """UPDATE ingestion_runs SET status='failed',finished_at=CURRENT_TIMESTAMP,
                       error_message=%s,records_read=%s,records_created=%s,
                       records_updated=%s,records_skipped=%s,metadata=%s WHERE id=%s""",
                (
                    str(failure)[:4000],
                    summary_count(progress, "records_read"),
                    summary_count(progress, "records_created"),
                    summary_count(progress, "records_updated"),
                    summary_count(progress, "records_skipped"),
                    Json(
                        {
                            "failure_stage": failure.stage,
                            "committed_summary": dict(progress),
                        }
                    ),
                    self.run_id,
                ),
            )
            self.connection.commit()
            return
        self.cursor.execute(
            """UPDATE ingestion_runs SET status='failed',finished_at=CURRENT_TIMESTAMP,
                   error_message=%s WHERE id=%s""",
            (str(failure)[:4000], self.run_id),
        )
        self.connection.commit()


def create_run(
    connection: PgConnection,
    cursor: PgCursor,
    *,
    source_code: str,
    job_name: str,
    locked: bool,
) -> PostgresIngestionRun:
    cursor.execute("SELECT id FROM data_sources WHERE code=%s", (source_code,))
    source = cursor.fetchone()
    if source is None:
        raise UnknownIngestionSourceError(source_code=source_code)
    cursor.execute(
        """INSERT INTO ingestion_runs
               (source_id,job_name,status,metadata,finished_at,error_message)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (
            source[0],
            job_name,
            "running" if locked else "cancelled",
            Json({"started_by": "schema-native-loader"}),
            None if locked else datetime.now(timezone.utc),
            None if locked else "Another run already holds the ingestion lock",
        ),
    )
    row = cursor.fetchone()
    assert row is not None
    connection.commit()
    return PostgresIngestionRun(connection=connection, cursor=cursor, run_id=row[0])


@dataclass(slots=True, kw_only=True, frozen=True)
class RunUnlocker:
    connection: PgConnection
    cursor: PgCursor
    job_name: str

    def __call__(self) -> None:
        self.connection.rollback()
        self.cursor.execute(
            "SELECT pg_advisory_unlock(%s)", (advisory_lock_key(self.job_name),)
        )
        self.connection.commit()


def close_run_resources(
    operations: tuple[Callable[[], object], ...], primary: BaseException | None
) -> None:
    failure = primary
    for operation in operations:
        try:
            operation()
        except BaseException as cleanup:
            if failure is None:
                failure = cleanup
                continue
            failure.add_note(f"Ingestion cleanup also failed: {cleanup!r}")
    if primary is None and failure is not None:
        raise failure


@contextmanager
def open_ingestion_run(
    *,
    source_code: str,
    job_name: str,
    connection_factory: Callable[[], PgConnection] = connect_database,
) -> Generator[PostgresIngestionRun]:
    connection = connection_factory()
    cursor: PgCursor | None = None
    locked = False
    primary: BaseException | None = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT pg_try_advisory_lock(%s)", (advisory_lock_key(job_name),)
        )
        row = cursor.fetchone()
        assert row is not None
        locked = bool(row[0])
        run = create_run(
            connection,
            cursor,
            source_code=source_code,
            job_name=job_name,
            locked=locked,
        )
        if not locked:
            raise ConcurrentIngestionError(job_name=job_name)
        yield run
    except BaseException as failure:
        primary = failure
        raise
    finally:
        operations: list[Callable[[], object]] = []
        if cursor is not None:
            if locked:
                operations.append(
                    RunUnlocker(connection=connection, cursor=cursor, job_name=job_name)
                )
            operations.append(cursor.close)
        operations.append(connection.close)
        close_run_resources(tuple(operations), primary)

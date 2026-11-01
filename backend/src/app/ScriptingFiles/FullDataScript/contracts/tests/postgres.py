"""Disposable PostgreSQL contract lifecycle scenarios."""

from _thread import LockType
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from app.ScriptingFiles.FullDataScript.contracts.tests.fixtures import SavedResponse
from psycopg2.extensions import connection as PgConnection
from sqlalchemy import text
from app.config import DatabaseSettings
from app.database import connect_database, open_database_cursor
from app.shared.cleanup import complete_cleanup


type ContractCounts = tuple[int, int, int]


@dataclass(slots=True, kw_only=True, frozen=True)
class HistoricalFixtureSession:
    body: str
    calls: list[str] = field(default_factory=list)
    lock: LockType = field(default_factory=Lock)

    def get(self, url: str, *, timeout: float) -> SavedResponse:
        nhl_id = url.rsplit(":", 1)[-1]
        with self.lock:
            self.calls.append(nhl_id)
        return SavedResponse(
            status_code=200,
            headers={},
            url=url,
            text=self.body.replace("8467514", nhl_id).replace(
                "datsyuk-2007", f"contract-{nhl_id}"
            ),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractDatabaseScenario:
    connection: PgConnection
    session: HistoricalFixtureSession

    def count_rows(self) -> ContractCounts:
        with open_database_cursor(self.connection) as cursor:
            cursor.execute(
                "SELECT (SELECT count(*) FROM contracts),(SELECT count(*) FROM contract_seasons),(SELECT count(*) FROM source_records)"
            )
            row = cursor.fetchone()
            assert row is not None
            return row[0], row[1], row[2]

    def latest_run(self) -> tuple[str, int, int, Mapping[str, object]]:
        with open_database_cursor(self.connection) as cursor:
            cursor.execute(
                "SELECT status,records_created,records_read,metadata FROM ingestion_runs WHERE job_name='populate_historical_contracts' ORDER BY id DESC LIMIT 1"
            )
            row = cursor.fetchone()
            assert row is not None
            return row[0], row[1], row[2], row[3]

    def install_batch_failure(self) -> None:
        with open_database_cursor(self.connection) as cursor:
            cursor.execute("""CREATE FUNCTION phase9_reject_late_contract() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF NEW.player_id=10101 THEN
                        RAISE EXCEPTION 'late contract batch failed';
                    END IF;
                    RETURN NEW;
                END $$""")
            cursor.execute(
                "CREATE TRIGGER phase9_late_contract BEFORE INSERT ON contracts FOR EACH ROW EXECUTE FUNCTION phase9_reject_late_contract()"
            )
        self.connection.commit()

    def remove_batch_failure(self) -> None:
        with open_database_cursor(self.connection) as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS phase9_late_contract ON contracts")
            cursor.execute("DROP FUNCTION IF EXISTS phase9_reject_late_contract()")
        self.connection.commit()


@contextmanager
def open_contract_scenario(
    settings: DatabaseSettings,
    session: HistoricalFixtureSession,
    *,
    cleanup_batch_failure: bool = False,
) -> Generator[ContractDatabaseScenario]:
    connection = connect_database(settings)
    scenario = ContractDatabaseScenario(connection=connection, session=session)
    primary: BaseException | None = None
    try:
        seed_contract_batch(connection)
        yield scenario
    except BaseException as failure:
        primary = failure
        raise
    finally:
        operations = (
            (connection.rollback, scenario.remove_batch_failure, connection.close)
            if cleanup_batch_failure
            else (connection.close,)
        )
        complete_cleanup(operations, primary)


def seed_contract_batch(connection: PgConnection) -> None:
    with open_database_cursor(connection) as cursor:
        cursor.execute("TRUNCATE teams,players,ingestion_runs RESTART IDENTITY CASCADE")
        cursor.execute(
            "INSERT INTO teams(id,abbreviation,name) VALUES (900,'DET','Detroit Red Wings')"
        )
        cursor.execute("""INSERT INTO players(id,first_name,last_name,primary_position)
            SELECT 10000+n,'Fixture','Player ' || n,'C' FROM generate_series(1,101) n""")
        cursor.execute("""INSERT INTO player_external_ids(player_id,source_id,external_id)
            SELECT 10000+n,ds.id,(8100000+n)::text FROM generate_series(1,101) n CROSS JOIN data_sources ds WHERE ds.code='nhl'""")
        cursor.execute("""INSERT INTO skater_season_stats(player_id,season_start_year,team_id,stat_scope,game_type,source_id,games_played)
            SELECT 10000+n,y,900,'TEAM',2,ds.id,1 FROM generate_series(1,101) n CROSS JOIN generate_series(2008,2009) y CROSS JOIN data_sources ds WHERE ds.code='nhl'""")
    connection.commit()


@dataclass(slots=True, kw_only=True, frozen=True)
class FixtureSession:
    body: str
    requests: list[str] = field(default_factory=list)

    @property
    def calls(self) -> int:
        return len(self.requests)

    def get(self, url, timeout):
        self.requests.append(url)
        return SavedResponse(status_code=200, headers={}, text=self.body, url=url)


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractPreviewScenario:
    session: FixtureSession
    before: ContractCounts


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractConflictScenario:
    before: ContractCounts
    after_preview: ContractCounts
    preview: Mapping[str, int]


def seed_player(
    engine, player_id: int, season: int = 2008, *, with_nhl_id: str = "8467514"
):
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO teams (id,abbreviation,name) VALUES (900,'DET','Detroit Red Wings')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO players (id,first_name,last_name,primary_position) VALUES (:id,'Pavel','Datsyuk','C')"
            ),
            {"id": player_id},
        )
        source_id = connection.execute(
            text("SELECT id FROM data_sources WHERE code='nhl'")
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO player_external_ids (player_id,source_id,external_id) VALUES (:p,:s,:e)"
            ),
            {"p": player_id, "s": source_id, "e": with_nhl_id},
        )
        for target_season in (season, season + 1):
            connection.execute(
                text(
                    """INSERT INTO skater_season_stats
                           (player_id,season_start_year,team_id,stat_scope,
                            game_type,source_id,games_played)
                       VALUES (:p,:y,NULL,'TOTAL',2,:s,50)"""
                ),
                {"p": player_id, "y": target_season, "s": source_id},
            )


def count_contract_rows(engine):
    with engine.connect() as connection:
        return tuple(
            connection.execute(
                text(
                    "SELECT (SELECT count(*) FROM contracts),(SELECT count(*) FROM contract_seasons),(SELECT count(*) FROM source_records WHERE entity_type='capspace_player_profile')"
                )
            ).one()
        )

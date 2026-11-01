"""DB-API transaction ownership against an explicitly disposable database."""

from uuid import uuid4
import psycopg2
from psycopg2 import sql
import pytest
from app.config import AppEnvironment, DatabaseSettings
from app.database import database_transaction
from app.shared.tests.resources import (
    TransactionScenario,
)


@pytest.mark.integration
class TestDatabaseTransactions:
    @pytest.fixture
    def scenario(self, disposable_database_url):
        database_url = disposable_database_url
        table = f"transaction_probe_{uuid4().hex}"
        settings = DatabaseSettings(
            environment=AppEnvironment.DEV, database_url=database_url
        )
        connection = psycopg2.connect(database_url)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("CREATE TABLE {} (value integer)").format(
                        sql.Identifier(table)
                    )
                )
            connection.commit()
            yield TransactionScenario(settings=settings, table=table)
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(table))
                )
            connection.commit()
            connection.close()

    def test_success_commits_and_closes(self, scenario):
        with database_transaction(scenario.settings) as connection:
            scenario.insert_row(connection)
        assert connection.closed != 0
        assert scenario.count_rows() == 1

    def test_failure_rolls_back_and_closes(self, scenario):
        with pytest.raises(RuntimeError, match="transaction failed"):
            with database_transaction(scenario.settings) as connection:
                scenario.insert_row(connection)
                raise RuntimeError("transaction failed")
        assert connection.closed != 0
        assert scenario.count_rows() == 0

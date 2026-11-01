"""DB-API transaction ownership against an explicitly disposable database."""

from uuid import uuid4
from psycopg2 import sql
import pytest
import logging
from app.config import AppEnvironment, DatabaseSettings
from app.database import open_database_cursor, open_database_transaction
from app.shared.observability.domain import InvocationContext
from app.shared.tests.resources import (
    TransactionScenario,
)


@pytest.mark.integration
class TestDatabaseTransactions:
    @pytest.fixture
    def context(self, caplog):
        caplog.set_level(logging.INFO)
        return InvocationContext(
            invocation_id="database-probe", source="transaction_probe", started_ns=0
        )

    @pytest.fixture
    def scenario(self, disposable_database_url):
        database_url = disposable_database_url
        table = f"transaction_probe_{uuid4().hex}"
        settings = DatabaseSettings(
            environment=AppEnvironment.DEV, database_url=database_url
        )
        with (
            open_database_transaction(settings) as connection,
            open_database_cursor(connection) as cursor,
        ):
            cursor.execute(
                sql.SQL("CREATE TABLE {} (value integer)").format(sql.Identifier(table))
            )
        try:
            yield TransactionScenario(settings=settings, table=table)
        finally:
            with (
                open_database_transaction(settings) as connection,
                open_database_cursor(connection) as cursor,
            ):
                cursor.execute(
                    sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(table))
                )

    def test_success_commits_and_closes(self, scenario, context, caplog):
        with open_database_transaction(
            scenario.settings, context=context
        ) as connection:
            scenario.insert_row(connection)
        assert connection.closed != 0
        assert scenario.count_rows() == 1
        assert [getattr(record, "event", None) for record in caplog.records] == [
            "transaction.committed"
        ]

    def test_failure_rolls_back_and_closes(self, scenario, context, caplog):
        with pytest.raises(RuntimeError, match="transaction failed"):
            with open_database_transaction(
                scenario.settings, context=context
            ) as connection:
                scenario.insert_row(connection)
                raise RuntimeError("transaction failed")
        assert connection.closed != 0
        assert scenario.count_rows() == 0
        assert [getattr(record, "event", None) for record in caplog.records] == [
            "transaction.rolled_back"
        ]

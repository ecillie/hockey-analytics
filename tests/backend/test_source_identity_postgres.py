"""Real persistence links canonical IDs across sources and repeated snapshots."""

import pytest

from app.config import AppEnvironment, DatabaseSettings
from app.database import open_database_cursor, open_database_transaction
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    PlayerKind,
    select_stat_layout,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.domain import (
    MoneyPuckSnapshot,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.repository import (
    PostgresMoneyPuckRepository,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.services import (
    normalize_row,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.domain import (
    NhlStatsSnapshot,
    StatsJob,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.repository import (
    PostgresNhlStatsRepository,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.services import (
    normalize_stat_row,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.policy import (
    RowPolicy,
    validate_rows,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.tests.scenarios import (
    IdentityPersistence,
    IdentityRepositories,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.tests.identities import (
    build_identity_rows,
)


@pytest.mark.integration
class TestCanonicalPersistence:
    @pytest.fixture
    def transaction(self, disposable_database_url):
        settings = DatabaseSettings(
            environment=AppEnvironment.DEV, database_url=disposable_database_url
        )

        def open_transaction(*, context=None):
            return open_database_transaction(settings, context=context)

        return open_transaction

    @pytest.fixture(
        params=[
            pytest.param(PlayerKind.SKATER, id="skater"),
            pytest.param(PlayerKind.GOALIE, id="goalie"),
        ]
    )
    def scenario(self, request, transaction):
        with transaction() as connection, open_database_cursor(connection) as cursor:
            cursor.execute(
                "TRUNCATE teams, players, ingestion_runs RESTART IDENTITY CASCADE"
            )
        kind = request.param
        incoming = build_identity_rows(7)
        rows, report = validate_rows(
            incoming.moneypuck,
            RowPolicy(
                source="MoneyPuck",
                required_fields=("playerId", "season"),
                grain_fields=("playerId", "season", "team", "situation"),
                integer_fields=frozenset({"playerId", "season"}),
            ),
        )
        advanced, basic = (
            select_stat_layout(kind, advanced=True),
            select_stat_layout(kind, advanced=False),
        )
        return IdentityPersistence(
            moneypuck=MoneyPuckSnapshot(
                rows=tuple(normalize_row(row, kind, advanced) for row in rows),
                quality=(report,),
            ),
            nhl=NhlStatsSnapshot(
                rows=tuple(
                    normalize_stat_row(
                        row, StatsJob(kind=kind, season=2025, game_type=2), basic
                    )
                    for row in incoming.nhl
                )
            ),
            expected_puck_hash=incoming.moneypuck_hashes[-1],
            expected_nhl_hash=incoming.nhl_hashes[-1],
            advanced_table=advanced.table,
            basic_table=basic.table,
        )

    @pytest.fixture
    def repositories(self, transaction):
        return IdentityRepositories(
            moneypuck=PostgresMoneyPuckRepository(transaction=transaction),
            nhl=PostgresNhlStatsRepository(transaction=transaction),
        )

    def test_aliases_share_one_player_and_one_stat_grain_across_repeat_ingestion(
        self, scenario, repositories, transaction
    ):
        puck, nhl = repositories.moneypuck, repositories.nhl
        assert puck.persist(scenario.moneypuck).counts.records_created == 1
        assert puck.persist(scenario.moneypuck).counts.records_created == 0
        first = nhl.persist(scenario.nhl)
        assert first.counts.records_created == 1
        assert first.counts.records_skipped == 4
        assert nhl.persist(scenario.nhl).counts.records_created == 0
        with transaction() as connection, open_database_cursor(connection) as cursor:
            cursor.execute("SELECT count(*) FROM players")
            assert cursor.fetchone() == (1,)
            cursor.execute(
                "SELECT count(*), count(DISTINCT player_id), array_agg(DISTINCT external_id) FROM player_external_ids"
            )
            assert cursor.fetchone() == (2, 1, ["7"])
            cursor.execute(f"SELECT source_row_hash FROM {scenario.advanced_table}")
            assert cursor.fetchall() == [(scenario.expected_puck_hash,)]
            cursor.execute(f"SELECT source_row_hash FROM {scenario.basic_table}")
            assert cursor.fetchall() == [(scenario.expected_nhl_hash,)]

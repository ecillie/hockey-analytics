"""Committed batches, failed run accounting, and lock ownership in PostgreSQL."""

from collections.abc import Generator
from pathlib import Path
import logging

import pytest
from app.database import connect_database
from app.ScriptingFiles.FullDataScript import capspace
from app.ScriptingFiles.FullDataScript.tracking.domain import IngestionContext
from app.shared.observability.domain import InvocationContext
from app.ScriptingFiles.FullDataScript.contracts.tests.postgres import (
    ContractDatabaseScenario,
    HistoricalFixtureSession,
    seed_contract_batch,
)
from app.ScriptingFiles.FullDataScript.tracking.errors import (
    ConcurrentIngestionError,
    IngestionBatchError,
    UnknownIngestionSourceError,
)
from app.ScriptingFiles.FullDataScript.tracking.repository import (
    build_advisory_lock_key,
    open_ingestion_run,
)


@pytest.mark.integration
class TestCommittedContractBatches:
    @pytest.fixture
    def logging_context(self, caplog):
        caplog.set_level(logging.INFO)
        return IngestionContext(
            invocation=InvocationContext(
                invocation_id="contract-invocation",
                source="contract_probe",
                started_ns=0,
            ),
            source="capspace",
            stage="historical",
        )

    @pytest.fixture
    def scenario(self, disposable_database_url) -> Generator[ContractDatabaseScenario]:
        connection = connect_database()
        seed_contract_batch(connection)
        body = (
            Path(__file__)
            .parent.joinpath("fixtures", "ingestion", "capspace_datsyuk.html")
            .read_text()
        )
        scenario = ContractDatabaseScenario(
            connection=connection, session=HistoricalFixtureSession(body=body)
        )
        try:
            yield scenario
        finally:
            connection.rollback()
            scenario.remove_batch_failure()
            connection.close()

    @pytest.fixture
    def failing_batch(self, scenario):
        scenario.install_batch_failure()
        return scenario

    def test_committed_hundred_survive_later_failure_and_resume(
        self, failing_batch, logging_context, caplog
    ):
        with pytest.raises(
            IngestionBatchError, match="late contract batch failed"
        ) as raised:
            capspace.ingest_historical_contracts(
                failing_batch.session,
                first_season=2008,
                last_season=2009,
                context=logging_context,
            )

        assert raised.value.committed_summary["batches_processed"] == 1
        assert failing_batch.count_rows() == (100, 200, 100)
        status, created, read, metadata = failing_batch.latest_run()
        assert (status, created, read) == ("failed", 300, 300)
        assert metadata["failure_stage"] == "persist"
        assert metadata["committed_summary"]["processed_player_seasons"] == 200
        batches = [
            record
            for record in caplog.records
            if getattr(record, "event", None) == "ingestion.batch_committed"
        ]
        assert len(batches) == 1
        assert batches[0].committed == created == 300
        finished = [
            record
            for record in caplog.records
            if getattr(record, "event", None) == "ingestion.finished"
        ]
        assert len(finished) == 1
        assert finished[0].outcome == "failed"
        assert finished[0].committed == created
        assert batches[0].run_id == finished[0].run_id
        assert batches[0].invocation_id == "contract-invocation"
        caplog.clear()
        failing_batch.remove_batch_failure()

        result = capspace.ingest_historical_contracts(
            failing_batch.session,
            first_season=2008,
            last_season=2009,
            context=logging_context,
        )

        assert result["candidate_players"] == 1
        assert result["remaining_uncovered_player_seasons"] == 0
        assert failing_batch.count_rows() == (101, 202, 101)
        assert len(failing_batch.session.calls) == 102
        assert failing_batch.latest_run()[0] == "succeeded"
        resumed = [
            record
            for record in caplog.records
            if getattr(record, "event", None) == "ingestion.finished"
        ]
        assert resumed[0].outcome == "completed"
        assert resumed[0].run_id != finished[0].run_id

    def test_preview_mutates_neither_contracts_snapshots_nor_tracking(
        self, scenario, logging_context, caplog
    ):
        summary = capspace.preview_historical_contracts(
            scenario.session,
            first_season=2008,
            last_season=2009,
            context=logging_context,
        )

        assert summary["candidate_player_seasons"] == 202
        assert summary["records_created"] == 0
        assert scenario.count_rows() == (0, 0, 0)
        assert len(scenario.session.calls) == 101
        with scenario.connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM ingestion_runs")
            assert cursor.fetchone() == (0,)
        batches = [
            record
            for record in caplog.records
            if getattr(record, "event", None) == "ingestion.batch_previewed"
        ]
        assert len(batches) == 2
        assert all(record.committed == 0 for record in batches)
        assert not any(
            getattr(record, "event", None) == "ingestion.batch_committed"
            for record in caplog.records
        )

    def test_unknown_source_releases_lock_and_control_resources(self, scenario):
        with pytest.raises(UnknownIngestionSourceError):
            with open_ingestion_run(
                source_code="missing-phase9-source", job_name="phase9-unknown"
            ):
                raise AssertionError("unknown source entered ingestion")
        with scenario.connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(%s)",
                (build_advisory_lock_key("phase9-unknown"),),
            )
            assert cursor.fetchone() == (True,)
            cursor.execute(
                "SELECT pg_advisory_unlock(%s)",
                (build_advisory_lock_key("phase9-unknown"),),
            )

    def test_overlap_is_cancelled_then_lock_can_be_reacquired(self, scenario):
        with open_ingestion_run(
            source_code="capspace", job_name="phase9-overlap"
        ) as run:
            with pytest.raises(ConcurrentIngestionError):
                with open_ingestion_run(
                    source_code="capspace", job_name="phase9-overlap"
                ):
                    raise AssertionError("overlap entered ingestion")
            run.succeed({"records_created": 3})
        assert run.connection.closed != 0
        assert run.cursor.closed
        with open_ingestion_run(
            source_code="capspace", job_name="phase9-overlap"
        ) as resumed:
            resumed.succeed({"records_created": 0})
        with scenario.connection.cursor() as cursor:
            cursor.execute(
                "SELECT status FROM ingestion_runs WHERE job_name='phase9-overlap' ORDER BY id"
            )
            assert cursor.fetchall() == [("succeeded",), ("cancelled",), ("succeeded",)]


@pytest.mark.integration
class TestContractSourceOwnership:
    @pytest.fixture
    def scenario(self, disposable_database_url) -> Generator[ContractDatabaseScenario]:
        connection = connect_database()
        seed_contract_batch(connection)
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO contracts(player_id,source_id,external_id,start_season,end_season,term_years,total_value_cents)
                SELECT 10101,id,'contract-8100001',2008,2009,7,4690000000 FROM data_sources WHERE code='capspace'""")
        connection.commit()
        body = (
            Path(__file__)
            .parent.joinpath("fixtures", "ingestion", "capspace_datsyuk.html")
            .read_text()
        )
        try:
            yield ContractDatabaseScenario(
                connection=connection, session=HistoricalFixtureSession(body=body)
            )
        finally:
            connection.close()

    def test_same_source_id_for_another_player_is_a_conflict(self, scenario):
        result = capspace.ingest_historical_contracts(
            scenario.session, first_season=2008, last_season=2009, player_id=10001
        )

        assert result["reconciliation_conflicts"] == 1
        assert result["records_created"] == 0
        assert scenario.count_rows() == (1, 0, 1)
        with scenario.connection.cursor() as cursor:
            cursor.execute("SELECT player_id FROM contracts")
            assert cursor.fetchone() == (10101,)

    def test_empty_legacy_nhl_id_stays_an_unfetched_missing_identity(self, scenario):
        with scenario.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE player_external_ids SET external_id='' WHERE player_id=10001"
            )
        scenario.connection.commit()

        result = capspace.ingest_historical_contracts(
            scenario.session, first_season=2008, last_season=2009, player_id=10001
        )

        assert result["players_without_nhl_ids"] == 1
        assert result["profiles_requested"] == 0
        assert result["records_created"] == 0
        assert scenario.session.calls == []
        with scenario.connection.cursor() as cursor:
            cursor.execute("SELECT external_key,payload->>'status' FROM source_records")
            assert cursor.fetchone() == ("10001", "no_nhl_id")

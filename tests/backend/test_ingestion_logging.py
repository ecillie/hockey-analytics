"""Safe durable identity and independent contexts across concurrent workers."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO, StringIO
import json
import logging
from threading import Barrier

import pytest
import requests
from urllib3.response import HTTPResponse
from urllib3.util.retry import Retry, RequestHistory

from app.shared.observability.domain import (
    InvocationContext,
    LogFormat,
    LogLevel,
    LoggingSettings,
)
from app.shared.observability.sinks import build_diagnostic_handler
from app.ScriptingFiles.FullDataScript import capspace, ingestion, ingestion_tracking
from app.ScriptingFiles.FullDataScript.source_ingestion.tests.responses import (
    SessionLifecycle,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.http import SessionSourceClient
from app.ScriptingFiles.FullDataScript.source_ingestion.tests.fakes import (
    ManagedSession,
)
from app.shared.tests.fakes import StageOutcome
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import PlayerKind
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.domain import (
    NhlStatsOptions,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.services import (
    NhlStatsService,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.tests.fakes import (
    MemoryNhlStatsRepository,
    MemorySourceClient,
    OwnedClientFactory,
)
from app.ScriptingFiles.FullDataScript.tracking.domain import IngestionContext
from app.ScriptingFiles.FullDataScript.tracking.errors import IngestionBatchError
from app.ScriptingFiles.FullDataScript.tracking.tests.fakes import TrackingScenario
from app.ScriptingFiles.FullDataScript.contracts.repository import http as profile_http
from app.ScriptingFiles.FullDataScript.contracts.domain import Candidate
from app.ScriptingFiles.FullDataScript.contracts.repository.http import (
    BorrowedProfileSessionFactory,
)
from app.ScriptingFiles.FullDataScript.contracts.services import ProfileFetcher
from app.ScriptingFiles.FullDataScript.contracts.tests.fixtures import (
    SavedResponse,
    read_contract_fixture,
)
from app.ScriptingFiles.FullDataScript.contracts.tests.transport import (
    ScriptedProfileSession,
    SleepRecorder,
)


@pytest.fixture(params=[pytest.param(format, id=format.value) for format in LogFormat])
def format(request):
    return request.param


@pytest.fixture(
    params=[
        pytest.param(level, id=level.name) for level in (LogLevel.INFO, LogLevel.DEBUG)
    ]
)
def level(request):
    return request.param


@pytest.fixture
def capture(format, level, monkeypatch):
    output = StringIO()
    handler = build_diagnostic_handler(
        LoggingSettings(format=format, level=level), output
    )
    target = logging.getLogger("app.ScriptingFiles.FullDataScript.tracking")
    monkeypatch.setattr(target, "handlers", [handler])
    monkeypatch.setattr(target, "level", logging.DEBUG)
    monkeypatch.setattr(target, "propagate", False)
    yield output
    handler.close()


@pytest.fixture
def context():
    return IngestionContext(
        invocation=InvocationContext(
            invocation_id="generated-invocation", source="command", started_ns=0
        ),
        source="caller",
        stage="caller",
    )


class TestDurableContext:
    @pytest.fixture
    def scenario(self, monkeypatch):
        scenario = TrackingScenario()
        monkeypatch.setattr(ingestion_tracking, "open_ingestion_run", scenario.open_run)
        return scenario

    @pytest.fixture
    def operation(self, scenario):
        return ingestion_tracking.tracked_ingestion("nhl", "stats")(scenario.ingest)

    def test_run_identity_is_enriched_without_mutating_caller(
        self, operation, context, scenario, capture
    ):
        assert operation(context=context) == {
            "records_read": 8,
            "records_created": 3,
            "records_updated": 2,
        }
        assert context.run_id is None
        assert context.source == "caller"
        assert scenario.events == ["work", "succeeded", "closed"]
        assert scenario.contexts[0].run_id == 17
        events = [
            json.loads(line.removeprefix("event "))
            for line in capture.getvalue().splitlines()
        ]
        assert [item["event"] for item in events] == [
            "ingestion.started",
            "ingestion.finished",
        ]
        assert {item["run_id"] for item in events} == {17}
        assert {item["source"] for item in events} == {"nhl"}
        assert {item["stage"] for item in events} == {"stats"}
        assert events[-1]["committed"] == 5
        assert events[-1]["fetched"] == 8
        assert events[-1]["outcome"] == "completed"

    @pytest.fixture
    def status_failure(self, monkeypatch):
        scenario = TrackingScenario(completion_failure=RuntimeError("status_secret"))
        monkeypatch.setattr(ingestion_tracking, "open_ingestion_run", scenario.open_run)
        return scenario

    @pytest.fixture
    def failing_operation(self, status_failure):
        return ingestion_tracking.tracked_ingestion("nhl", "stats")(
            status_failure.ingest
        )

    def test_status_failure_preserves_completed_work_counts(
        self, status_failure, failing_operation, context, capture
    ):
        with pytest.raises(RuntimeError) as raised:
            failing_operation(context=context)
        assert raised.value is status_failure.completion_failure
        assert status_failure.events == ["work", "succeeded", "failed", "closed"]
        events = [
            json.loads(line.removeprefix("event "))
            for line in capture.getvalue().splitlines()
        ]
        assert events[-1]["outcome"] == "failed"
        assert events[-1]["committed"] == 5
        assert events[-1]["fetched"] == 8
        assert "status_secret" not in capture.getvalue()


class TestTrackedFailures:
    @pytest.fixture(
        params=[
            pytest.param(False, id="status-recorded"),
            pytest.param(True, id="status-report-failed"),
        ]
    )
    def reporting_failure(self, request):
        return RuntimeError("reporting_secret") if request.param else None

    @pytest.fixture(
        params=[
            pytest.param("error", id="failed"),
            pytest.param("cancelled", id="cancelled"),
            pytest.param("partial", id="partial-commit"),
        ]
    )
    def failure(self, request):
        if request.param == "cancelled":
            return asyncio.CancelledError("payload_secret")
        if request.param == "partial":
            return IngestionBatchError(
                stage="persist",
                committed_summary={
                    "records_read": 4,
                    "records_created": 3,
                    "records_updated": 0,
                },
                failure=RuntimeError("payload_secret"),
            )
        return RuntimeError("payload_secret")

    @pytest.fixture
    def scenario(self, failure, reporting_failure, monkeypatch):
        scenario = TrackingScenario(
            failure=failure,
            reporting_failure=reporting_failure,
        )
        monkeypatch.setattr(ingestion_tracking, "open_ingestion_run", scenario.open_run)
        return scenario

    @pytest.fixture
    def operation(self, scenario):
        return ingestion_tracking.tracked_ingestion("capspace", "contracts")(
            scenario.ingest
        )

    def test_original_failure_and_committed_progress_are_preserved(
        self, operation, context, scenario, failure, capture, level
    ):
        with pytest.raises(type(failure)) as raised:
            operation(context=context)
        assert raised.value is failure
        assert scenario.events == ["work", "failed", "closed"]
        if scenario.reporting_failure is not None:
            assert "reporting_secret" in failure.__notes__[0]
        events = [
            json.loads(line.removeprefix("event "))
            for line in capture.getvalue().splitlines()
        ]
        finished = [item for item in events if item["event"] == "ingestion.finished"]
        cancelled = (
            isinstance(failure, asyncio.CancelledError)
            and scenario.reporting_failure is None
        )
        assert len(finished) == (0 if cancelled and level is LogLevel.INFO else 1)
        if len(finished) > 0:
            assert finished[0]["outcome"] == ("cancelled" if cancelled else "failed")
            assert finished[0].get("committed") == (
                3 if isinstance(failure, IngestionBatchError) else None
            )
        assert not any(item["severity"] == "ERROR" for item in events)
        assert "secret" not in capture.getvalue()


class TestConcurrentWorkerContext:
    @pytest.fixture
    def services(self, source_stat_row):
        barrier = Barrier(4)
        pages = {
            (f"https://api.nhle.com/stats/rest/en/{kind}/summary", 0): {
                "data": [source_stat_row]
            }
            for kind in PlayerKind
        }
        return tuple(
            NhlStatsService(
                client_factory=OwnedClientFactory(
                    client=MemorySourceClient(pages=pages), barrier=barrier
                ),
                repository=MemoryNhlStatsRepository(),
                options=NhlStatsOptions(
                    first_season=season, last_season=season, workers=2
                ),
                context=IngestionContext(
                    invocation=InvocationContext(
                        invocation_id=f"invocation-{season}",
                        source="command",
                        started_ns=0,
                    ),
                    source="nhl",
                    stage="stats",
                    run_id=season,
                ),
            )
            for season in (2024, 2025)
        )

    def test_concurrent_jobs_retain_their_own_run_and_season(
        self, services, capture, level
    ):
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = tuple(executor.submit(service.ingest) for service in services)
            results = tuple(future.result(timeout=10) for future in futures)
        assert [result.counts.records_read for result in results] == [4, 4]
        events = [
            json.loads(line.removeprefix("event "))
            for line in capture.getvalue().splitlines()
        ]
        workers = [
            item for item in events if item["event"] == "ingestion.worker_finished"
        ]
        assert len(workers) == (8 if level is LogLevel.DEBUG else 0)
        assert all(
            item["invocation_id"] == f"invocation-{item['run_id']}"
            and item["season"] == item["run_id"]
            for item in workers
        )
        assert {item["run_id"] for item in events} == {2024, 2025}
        assert all(
            len(line.encode()) < 8192 for line in capture.getvalue().splitlines()
        )


class TestRunnerCleanup:
    @pytest.fixture(
        params=[
            pytest.param("failed", id="failed-work"),
            pytest.param("cancelled", id="cancelled-work"),
            pytest.param("completed", id="completed-work"),
        ]
    )
    def primary(self, request):
        if request.param == "completed":
            return None
        if request.param == "cancelled":
            return asyncio.CancelledError("primary_secret")
        return RuntimeError("primary_secret")

    @pytest.fixture
    def session(self):
        return SessionLifecycle(failure=RuntimeError("cleanup_secret"))

    @pytest.fixture
    def runner(self, session, primary, monkeypatch):
        monkeypatch.setattr(ingestion, "init_db", StageOutcome(result=None))
        monkeypatch.setattr(ingestion, "http_session", StageOutcome(result=session))
        for name in (
            "ingest_nhl_rosters",
            "ingest_nhl_stats",
            "ingest_capwages",
            "ingest_schedule",
        ):
            monkeypatch.setattr(ingestion, name, StageOutcome(result={}))
        monkeypatch.setattr(
            ingestion, "ingest_moneypuck", StageOutcome(result={}, failure=primary)
        )
        monkeypatch.setattr(
            capspace, "ingest_historical_contracts", StageOutcome(result={})
        )
        return ingestion.run_all

    def test_cleanup_keeps_primary_failure_or_reports_its_own(
        self, runner, session, primary
    ):
        expected = session.failure if primary is None else primary
        with pytest.raises(type(expected)) as raised:
            runner()
        assert raised.value is expected
        assert session.closures == [True]
        if primary is not None:
            assert "cleanup_secret" in primary.__notes__[0]


class TestProfileRetryContext:
    @pytest.fixture(
        params=[
            pytest.param(False, id="http-retry"),
            pytest.param(True, id="timeout-retry"),
        ]
    )
    def session(self, request):
        transient = (
            requests.Timeout("url_secret")
            if request.param
            else SavedResponse(
                status_code=429,
                headers={"Retry-After": "2"},
                text="payload_secret",
                url="https://capspace.com/person/nhl:8467514?token=url_secret",
            )
        )
        return ScriptedProfileSession(
            responses=(
                transient,
                SavedResponse(
                    status_code=200,
                    headers={},
                    text=read_contract_fixture("capspace_datsyuk.html"),
                    url="https://capspace.com/person/nhl:8467514?token=url_secret",
                ),
            )
        )

    @pytest.fixture
    def sleep(self, monkeypatch):
        recorder = SleepRecorder()
        monkeypatch.setattr(profile_http.time, "sleep", recorder)
        return recorder

    @pytest.fixture
    def fetcher(self, session, context):
        return ProfileFetcher(
            session_factory=BorrowedProfileSessionFactory(session=session),
            context=replace(context, source="capspace", run_id=17),
        )

    @pytest.fixture
    def candidate(self):
        return Candidate(
            player_id=1,
            first_name="Pavel",
            last_name="Datsyuk",
            nhl_id="8467514",
            missing_seasons=(2008, 2009),
        )

    def test_retry_decision_keeps_worker_identity_without_url_or_payload(
        self, fetcher, candidate, capture, level, sleep, session
    ):
        results = fetcher.fetch_profiles((candidate,), workers=1)
        assert len(results) == 1
        assert results[0].covers_target
        assert len(session.calls) == 2
        assert len(sleep.delays) == 1
        events = [
            json.loads(line.removeprefix("event "))
            for line in capture.getvalue().splitlines()
        ]
        assert len(events) == (1 if level is LogLevel.DEBUG else 0)
        if len(events) > 0:
            assert events[0]["event"] == "ingestion.retry_scheduled"
            assert events[0]["attempt"] == 2
            assert events[0]["run_id"] == 17
            assert events[0]["invocation_id"] == "generated-invocation"
        assert "secret" not in capture.getvalue()


class TestAdapterRecovery:
    @pytest.fixture(
        params=[
            pytest.param(False, id="first-attempt"),
            pytest.param(True, id="retried"),
        ]
    )
    def retried(self, request):
        return request.param

    @pytest.fixture(
        params=[pytest.param("json", id="json"), pytest.param("csv", id="csv")]
    )
    def kind(self, request):
        return request.param

    @pytest.fixture
    def client(self, context, retried):
        history = tuple(
            RequestHistory(
                method="GET",
                url="https://feed.invalid?token=url_secret",
                error=None,
                status=503,
                redirect_location=None,
            )
            for _ in range(2 if retried else 0)
        )
        with (
            BytesIO(b'{"value":"payload_secret"}') as body,
            requests.Response() as response,
        ):
            response.status_code = 200
            response.raw = HTTPResponse(
                body=body,
                preload_content=False,
                retries=Retry(total=4, history=history),
            )
            yield SessionSourceClient(
                session=ManagedSession(response=response),
                context=replace(context, source="nhl", run_id=17),
            )

    def test_native_retry_history_produces_only_safe_recovery_count(
        self, client, retried, kind, capture, level
    ):
        result = (
            client.get_json("https://feed.invalid?token=url_secret")
            if kind == "json"
            else client.get_csv("https://feed.invalid?token=url_secret")
        )
        assert result == (
            {"value": "payload_secret"}
            if kind == "json"
            else '{"value":"payload_secret"}'
        )
        events = [
            json.loads(line.removeprefix("event "))
            for line in capture.getvalue().splitlines()
        ]
        assert sum(item["event"] == "ingestion.request_started" for item in events) == (
            level is LogLevel.DEBUG
        )
        recovered = [
            item for item in events if item["event"] == "ingestion.request_recovered"
        ]
        assert len(recovered) == retried
        if len(recovered) > 0:
            assert recovered[0]["attempt"] == 3
            assert recovered[0]["severity"] == "WARNING"
            assert recovered[0]["run_id"] == 17
            assert recovered[0]["invocation_id"] == "generated-invocation"
        assert "secret" not in capture.getvalue()

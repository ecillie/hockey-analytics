"""Phase 5 acceptance: real entrypoints, isolated context, and secret-free output."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import StringIO
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.observability import (
    configure_logging, log_context, log_event, workflow_context,
)
from app.request_logging import RequestLoggingMiddleware
from app.jobs.shared.execution import JobOperation, writer_session
from app.jobs.shared.source_requests import RequestPolicy, Response, SourceClient, SourceRequestError
from app.database_setup.run_setup import plan_setup, run_setup
from .execution_fixtures import TEAM, batch, config, executor, source
from .contract_store import ContractStore
from .test_execution_foundation import InterruptingStore
from .test_api import StubService

SECRET = "sensitive-test-value-do-not-emit"
logger = logging.getLogger(__name__)


@pytest.fixture
def diagnostics(monkeypatch):
    root = logging.getLogger()
    saved = (root.handlers[:], root.level, logging.raiseExceptions)
    children = {name: (child.handlers[:], child.level, child.propagate, child.disabled)
                for name, child in logging.Logger.manager.loggerDict.items()
                if isinstance(child, logging.Logger)}
    stream = StringIO()
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("LOG_FILE", "")
    configure_logging(level="DEBUG", stream=stream)
    yield stream
    for handler in root.handlers:
        if isinstance(handler, RotatingFileHandler):
            handler.close()
    root.handlers[:] = saved[0]
    root.setLevel(saved[1])
    logging.raiseExceptions = saved[2]
    logging.captureWarnings(False)
    for name, state in children.items():
        child = logging.getLogger(name)
        child.handlers[:], child.level, child.propagate, child.disabled = state


def events(stream, event=None):
    values = [json.loads(line) for line in stream.getvalue().splitlines()]
    return values if event is None else [value for value in values if value["event"] == event]


def test_json_schema_configured_levels_workflow_metadata_and_no_duplicates(diagnostics, monkeypatch):
    old_stream = StringIO()
    child = logging.getLogger("uvicorn.error")
    child.addHandler(logging.StreamHandler(old_stream))
    child.propagate = False
    monkeypatch.setenv("LOG_LEVEL", "warning")
    configure_logging(stream=diagnostics)
    configure_logging(stream=diagnostics)
    log_event(logger, "job.started")
    log_event(child, "source.retry", level=logging.WARNING, attempt=1, delay_seconds=2)
    assert len(events(diagnostics)) == 1 and old_stream.getvalue() == ""
    value = events(diagnostics)[0]
    assert value["severity"] == "WARNING" and value["timestamp"].endswith("Z")
    assert value["environment"] == "dev" and value["attempt"] == 1
    assert len(logging.getLogger().handlers) == 1
    logging.getLogger("uvicorn.access").info("GET /?token=%s", SECRET)
    assert len(events(diagnostics)) == 1
    for key, value in {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2", "GITHUB_SHA": "a" * 40}.items():
        monkeypatch.setenv(key, value)
    assert workflow_context() == {"github_run_id": 123, "github_run_attempt": 2, "github_sha": "a" * 40}
    monkeypatch.setenv("GITHUB_SHA", SECRET)
    monkeypatch.setenv("GITHUB_RUN_ID", SECRET)
    assert workflow_context() == {"github_run_attempt": 2}
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        configure_logging(level=SECRET)
    with pytest.raises(ValueError, match="Unknown"):
        log_event(logger, SECRET)


def test_library_messages_args_sql_payloads_and_exception_chains_are_not_rendered(diagnostics):
    class Unprintable:
        def __str__(self):
            raise AssertionError("Logging interpolated raw arguments")
    try:
        try:
            raise ValueError(f"password={SECRET} raw payload")
        except ValueError as exc:
            raise OperationalError(f"SELECT '{SECRET}'", {"password": SECRET}, exc) from exc
    except OperationalError as exc:
        logging.getLogger("sqlalchemy.engine").exception("raw query %s", Unprintable(),
            extra={"password": SECRET, "request_body": SECRET})
        log_event(logger, "job.error", level=logging.ERROR, error=exc, password=SECRET, payload=SECRET)
    assert SECRET not in diagnostics.getvalue()
    values = events(diagnostics)
    assert values[0]["event"] == "library_log"
    assert [item["type"] for item in values[1]["exceptions"]] == ["OperationalError", "ValueError"]
    assert values[1]["exceptions"][0]["frames"][-1]["function"].startswith("test_library")
    assert "SELECT" not in diagnostics.getvalue() and "raw payload" not in diagnostics.getvalue()


def test_context_nested_resets_and_nonfinite_unknown_fields_are_discarded(diagnostics):
    request_id = str(uuid4())
    with log_context(request_id=request_id, environment="prod"):
        with pytest.raises(RuntimeError):
            with log_context(component="database", request_id="invalid"):
                log_event(logger, "database.committed", duration_ms=float("nan"), payload=SECRET,
                          route="/raw?password=" + SECRET, method=SECRET)
                raise RuntimeError(SECRET)
        log_event(logger, "job.started")
    log_event(logger, "job.finished")
    first, second, third = events(diagnostics)
    assert first["request_id"] == second["request_id"] == request_id
    assert first["component"] == "database" and first["method"] == "OTHER"
    assert "duration_ms" not in first and "route" not in first
    assert "request_id" not in third and third["environment"] == "dev"
    assert SECRET not in diagnostics.getvalue()


def test_api_requests_errors_and_unmatched_paths_keep_contract_and_no_secrets(diagnostics):
    from app.api.routes import get_service
    from app.main import create_app
    app = create_app()
    configure_logging(level="DEBUG", stream=diagnostics)
    stub = StubService()
    app.dependency_overrides[get_service] = lambda: stub
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/players/7?token=" + SECRET).status_code == 200
    # Invalid numeric query values are retained in the response by the existing
    # contract; diagnostics must not echo them.
    assert client.get("/api/players?pageSize=" + SECRET).status_code == 400
    assert client.get("/not-found/" + SECRET).status_code == 404
    stub.session.execute.side_effect = OperationalError("SELECT " + SECRET, {"token": SECRET}, Exception(SECRET))
    response = client.get("/api/health")
    assert response.status_code == 503 and response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    stub.players = Mock(side_effect=RuntimeError(SECRET))
    response = client.get("/api/players")
    assert response.status_code == 500 and response.json()["error"]["code"] == "INTERNAL_ERROR"
    requests = events(diagnostics, "api.request_completed")
    assert [value["status_code"] for value in requests] == [200, 400, 404, 503, 500]
    assert requests[0]["route"] == "/api/players/{player_id}"
    assert requests[2]["route"] == "unmatched"
    assert len({value["request_id"] for value in requests}) == 5
    assert all(value["duration_ms"] >= 0 for value in requests)
    assert events(diagnostics, "api.database_error")[0]["request_id"] == requests[3]["request_id"]
    assert requests[-1]["exceptions"][0]["type"] == "RuntimeError"
    assert SECRET not in diagnostics.getvalue()


def test_asgi_concurrent_request_context_streams_and_cancellation(diagnostics):
    async def scenario():
        ready, count = asyncio.Event(), 0
        async def application(scope, receive, send):
            nonlocal count
            scope["route"] = SimpleNamespace(path="/api/items/{item_id}")
            count += 1
            if count == 2:
                ready.set()
            await ready.wait()
            log_event(logger, "api.problem", status_code=400)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"a", "more_body": True})
            await send({"type": "http.response.body", "body": b"b"})
        middleware = RequestLoggingMiddleware(application)
        async def request():
            sent = []
            async def send(message):
                sent.append(message)
            await middleware({"type": "http", "method": "GET", "path": "/" + SECRET}, None, send)
            assert [item.get("body") for item in sent[1:]] == [b"a", b"b"]
        await asyncio.gather(request(), request())
        async def cancelled(scope, receive, send):
            raise asyncio.CancelledError(SECRET)
        with pytest.raises(asyncio.CancelledError):
            await RequestLoggingMiddleware(cancelled)({"type": "http", "method": "GET"}, None, None)
        seen = []
        async def lifespan(scope, receive, send):
            seen.append(scope["type"])
        await RequestLoggingMiddleware(lifespan)({"type": "lifespan"}, None, None)
        assert seen == ["lifespan"]
    asyncio.run(scenario())
    requests = events(diagnostics, "api.request_completed")
    assert len(requests) == 2 and requests[0]["request_id"] != requests[1]["request_id"]
    assert {item["request_id"] for item in events(diagnostics, "api.problem")} == {item["request_id"] for item in requests}
    assert events(diagnostics, "api.request_cancelled")[0]["exceptions"][0]["type"] == "CancelledError"
    assert SECRET not in diagnostics.getvalue()


@pytest.mark.parametrize("mode,enabled,registered,status", [
    ("initial", True, True, "succeeded"), ("validation", True, True, "succeeded"),
    ("initial", False, True, "disabled"), ("initial", True, False, "deferred"),
])
def test_job_lifecycle_logs_counts_scope_and_terminal_states(diagnostics, mode, enabled, registered, status):
    runner = executor(operations=None if registered else {})
    report = runner.run(config(mode=mode, enabled=enabled))
    started, finished = events(diagnostics, "job.started")[0], events(diagnostics, "job.finished")[0]
    assert started["job_run_id"] == finished["job_run_id"] == str(report.run.run_id)
    assert started["job"] == "teams_seasons" and started["mode"] == mode
    assert started["first_season"] == 2026 and started["game_types"] == [2, 3]
    assert finished["status"] == status and finished["read"] == report.run.counters.read
    assert finished["duration_ms"] >= 0
    if mode == "validation":
        assert not events(diagnostics, "job.checkpoint_committed")


def test_job_validation_failures_and_cancelled_partial_runs_are_diagnosable(diagnostics):
    def failing(ctx, cursor):
        yield batch(source("teams", TEAM), final=False)
        raise RuntimeError(SECRET)
    report = executor(operations={"teams_seasons": JobOperation(failing)}).run(config())
    assert report.run.status == "partial"
    assert events(diagnostics, "job.finished")[-1]["status"] == "partial"
    assert events(diagnostics, "job.error")[-1]["exceptions"][0]["type"] == "RuntimeError"
    def cancelled(ctx, cursor):
        raise KeyboardInterrupt(SECRET)
    report = executor(operations={"teams_seasons": JobOperation(cancelled)}).run(config())
    assert report.run.status == "cancelled"
    bad = batch(source("teams", {**TEAM, "team_id": SECRET}))
    report = executor(operations={"teams_seasons": JobOperation(lambda ctx, cursor: [bad])}).run(config())
    assert report.issues and events(diagnostics, "job.batch_validated")[-1]["issues"] == 1
    assert SECRET not in diagnostics.getvalue()


def test_checkpoint_retry_resume_and_setup_context(diagnostics):
    store = InterruptingStore()
    store.interrupt = False
    store.uncertain = True
    runner = executor(store)
    plan = plan_setup(selected=("teams_seasons", "player_profiles"), environment="dev",
                      target_environment="dev", current_season=2026, first_season=2026)
    report = run_setup(runner, plan)
    assert report.complete and events(diagnostics, "upload.retry")
    setup_id = events(diagnostics, "setup.started")[0]["setup_run_id"]
    assert all(item["setup_run_id"] == setup_id for item in events(diagnostics, "job.started"))
    assert events(diagnostics, "setup.finished")[0]["completed_jobs"] == 2
    retry = events(diagnostics, "upload.retry")[0]
    assert retry["job_run_id"] == str(report.reports[0].run.run_id) and retry["batch_id"]
    assert runner.run(config(resume=True)).run.status == "no_change"
    resumed = events(diagnostics, "job.resumed")[-1]
    assert resumed["checkpoint_complete"] and "setup_run_id" not in resumed
    with writer_session(runner.store, "dev", config().conflict_scopes):
        assert runner.run(config(mode="refresh")).run.status == "deferred"
    assert events(diagnostics, "job.started")[-1]["job_run_id"] == events(diagnostics, "job.finished")[-1]["job_run_id"]


def test_job_context_isolated_between_threads_and_reset_after_config_failure(diagnostics):
    barrier = Barrier(2)
    def collect(ctx, cursor):
        barrier.wait(timeout=3)
        log_event(logger, "source.request", source="fixture", status_code=200)
        return [batch()]
    def run():
        return executor(operations={"teams_seasons": JobOperation(collect)}).run(config())
    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(lambda _: run(), range(2)))
    assert len({item["job_run_id"] for item in events(diagnostics, "source.request")}) == 2
    assert {item["job_run_id"] for item in events(diagnostics, "job.finished")} == {str(r.run.run_id) for r in reports}
    runner = executor()
    runner.target_environment = "prod"
    with pytest.raises(ValueError):
        runner.run(config())
    log_event(logger, "source.request", source="fixture")
    assert "job_run_id" not in events(diagnostics, "source.request")[-1]


def test_source_retry_failure_malformed_json_and_url_redaction(diagnostics):
    values = iter([Response(429, SECRET.encode(), 1), TimeoutError(SECRET), Response(200, b"{}")])
    def transport(*args, **kwargs):
        value = next(values)
        if isinstance(value, Exception):
            raise value
        return value
    client = SourceClient({"fixture": RequestPolicy(minimum_interval_seconds=0)}, transport=transport,
                          clock=lambda: 100, pause=lambda _: None)
    assert client.json("fixture", "https://user:" + SECRET + "@fixture.invalid/?token=" + SECRET) == {}
    assert len(events(diagnostics, "source.retry")) == 2
    client.transport = lambda *args, **kwargs: Response(200, SECRET.encode())
    with pytest.raises(SourceRequestError):
        client.json("fixture", "https://fixture.invalid")
    assert events(diagnostics, "source.invalid_json")
    client.transport = lambda *args, **kwargs: Response(403, SECRET.encode())
    with pytest.raises(SourceRequestError):
        client.get("fixture", "https://fixture.invalid")
    assert events(diagnostics, "source.failed")[-1]["source"] == "fixture"
    assert SECRET not in diagnostics.getvalue()


def test_database_transaction_and_connection_errors_suppress_sql_credentials(diagnostics, monkeypatch):
    from app import database
    import psycopg2
    connection = Mock()
    monkeypatch.setattr(psycopg2, "connect", Mock(return_value=connection))
    with database.database_transaction():
        pass
    connection.commit.assert_called_once()
    assert events(diagnostics, "database.committed")
    with pytest.raises(RuntimeError):
        with database.database_transaction():
            raise RuntimeError(SECRET)
    connection.rollback.assert_called_once()
    assert events(diagnostics, "database.rolled_back")
    connection.rollback.side_effect = RuntimeError(SECRET)
    with pytest.raises(RuntimeError):
        with database.database_transaction():
            raise RuntimeError(SECRET)
    assert events(diagnostics, "database.rollback_failed")
    monkeypatch.setattr(psycopg2, "connect", Mock(side_effect=RuntimeError(SECRET)))
    with pytest.raises(RuntimeError):
        database.connect_database()
    assert events(diagnostics, "database.connection_failed")
    assert database.engine.hide_parameters is True
    assert SECRET not in diagnostics.getvalue()


def test_setup_snapshot_failure_and_invalid_configuration_are_logged(diagnostics):
    class UnavailableStore(ContractStore):
        def snapshot(self, *args, **kwargs):
            raise RuntimeError(SECRET)
    result = run_setup(executor(UnavailableStore()), (config(mode="validation"),))
    assert not result.complete and events(diagnostics, "setup.error")
    with pytest.raises(ValueError):
        run_setup(executor(), ())
    assert events(diagnostics, "setup.finished")[-1]["status"] == "failed"
    assert SECRET not in diagnostics.getvalue()


def test_cli_stdout_stderr_and_invalid_runtime_arguments_are_secret_free():
    root = Path(__file__).resolve().parents[2]
    args = [sys.executable, "-m", "app.jobs.teams_seasons", "--environment", "dev",
            "--current-season", "2026", "--runtime", "tests.execution_fixtures:create_runtime"]
    result = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["run"]["status"] == "succeeded" and report["checkpoint_count"] == 1
    logs = [json.loads(line) for line in result.stderr.splitlines()]
    assert [item["event"] for item in logs if item["event"].startswith("job.")] == ["job.started", "job.finished"]
    result = subprocess.run([*args, "--first-season", SECRET], cwd=root, capture_output=True, text=True, timeout=20)
    assert result.returncode == 2 and SECRET not in result.stderr and not result.stdout
    assert '"event": "cli.failed"' in result.stderr
    assert all(json.loads(line)["event"] == "cli.failed" for line in result.stderr.splitlines())


def test_cli_summary_hides_validation_input_error_cursor_and_coverage_details(diagnostics):
    from app.jobs.shared.cli import console_report, report_payload
    broken = batch(source("teams", {**TEAM, "team_id": SECRET}))
    report = executor(operations={"teams_seasons": JobOperation(lambda ctx, cursor: [broken])}).run(config())
    report = replace(report, error=SECRET, committed_cursors=({"password": SECRET},),
                     source_coverage=({"dataset": "teams", "status": "limited", "limitation": SECRET,
                                       "unknown_measurements": [SECRET], "enumerated_records": 1},))
    public = console_report(report)
    assert SECRET not in json.dumps(public)
    assert public["checkpoint_count"] == 1 and public["issues"][0]["code"] == "INVALID_RECORD"
    assert report_payload(report)["error"] == SECRET


def test_dev_file_uses_backend_relative_path_and_same_sanitized_json(diagnostics, monkeypatch, tmp_path):
    from app import observability
    monkeypatch.setattr(observability, "BACKEND_DIR", tmp_path / "backend")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOG_FILE", "logs/backend.txt")
    configure_logging(stream=diagnostics)
    try:
        raise RuntimeError(SECRET)
    except RuntimeError as exc:
        log_event(logger, "job.error", level=logging.ERROR, error=exc, password=SECRET)
    path = tmp_path / "backend/logs/backend.txt"
    text = path.read_text(encoding="utf-8")
    assert text == diagnostics.getvalue() and SECRET not in text
    assert json.loads(text)["exceptions"][0]["type"] == "RuntimeError"
    assert not (tmp_path / "logs/backend.txt").exists()


@pytest.mark.parametrize("environment", ["prod", "nonprod", "unknown"])
def test_file_ignored_outside_dev_even_when_ambient_env_is_dev(diagnostics, monkeypatch, tmp_path, environment):
    path = tmp_path / "must-not-create/backend.txt"
    monkeypatch.setenv("LOG_FILE", str(path))
    configure_logging(stream=diagnostics, environment=environment)
    log_event(logger, "job.started")
    assert not path.parent.exists() and len(logging.getLogger().handlers) == 1
    assert events(diagnostics)[0]["environment"] == environment


def test_dev_file_rotation_retention_levels_and_reconfiguration(diagnostics, monkeypatch, tmp_path):
    path = tmp_path / "backend.txt"
    monkeypatch.setenv("LOG_FILE", str(path))
    configure_logging(level="WARNING", stream=diagnostics)
    original = next(handler for handler in logging.getLogger().handlers if isinstance(handler, RotatingFileHandler))
    assert original.maxBytes == 5 * 1024 * 1024 and original.backupCount == 3
    configure_logging(level="WARNING", stream=diagnostics)
    assert original.stream is None
    log_event(logger, "job.started")
    log_event(logger, "source.retry", level=logging.WARNING, attempt=1)
    assert len(path.read_text().splitlines()) == len(events(diagnostics)) == 1
    current = next(handler for handler in logging.getLogger().handlers if isinstance(handler, RotatingFileHandler))
    current.maxBytes = 400
    for attempt in range(20):
        log_event(logger, "source.retry", level=logging.WARNING, attempt=attempt)
    assert {item.name for item in tmp_path.iterdir()} == {"backend.txt", "backend.txt.1", "backend.txt.2", "backend.txt.3"}
    assert all(json.loads(line)["event"] == "source.retry"
               for item in tmp_path.iterdir() for line in item.read_text().splitlines())
    monkeypatch.setenv("LOG_FILE", "")
    configure_logging(stream=diagnostics)
    assert current.stream is None and len(logging.getLogger().handlers) == 1


def test_invalid_file_path_fails_without_exposing_path_or_replacing_logging(diagnostics, monkeypatch, tmp_path):
    parent = tmp_path / SECRET
    parent.write_text("not a directory")
    monkeypatch.setenv("LOG_FILE", str(parent / "backend.txt"))
    original = logging.getLogger().handlers[:]
    with pytest.raises(ValueError, match="Unable to open LOG_FILE") as error:
        configure_logging(stream=diagnostics)
    assert SECRET not in str(error.value) and error.value.__suppress_context__
    assert logging.getLogger().handlers == original
    log_event(logger, "job.started")
    assert events(diagnostics)[0]["event"] == "job.started"


def test_cli_file_selection_uses_argument_environment_and_keeps_stdout_json(tmp_path):
    root = Path(__file__).resolve().parents[2]
    path = tmp_path / "backend.txt"
    environment = {**os.environ, "ENV": "dev", "LOG_FILE": str(path), "LOG_LEVEL": "INFO"}
    args = [sys.executable, "-m", "app.jobs.teams_seasons", "--current-season", "2026",
            "--runtime", "tests.execution_fixtures:create_runtime", "--validation-only"]
    result = subprocess.run([*args, "--environment", "nonprod"], cwd=root, env=environment,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 2 and not path.exists()
    assert all(json.loads(line)["environment"] == "nonprod" for line in result.stderr.splitlines())
    result = subprocess.run([*args, "--environment", "dev"], cwd=root, env=environment,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0 and json.loads(result.stdout)["run"]["status"] == "succeeded"
    assert path.read_text() == result.stderr

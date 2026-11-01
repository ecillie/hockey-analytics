"""Transaction diagnostics follow actual commit/rollback and preserve failures."""

import asyncio
from io import StringIO
import json
import logging

import pytest

from app import database
from app.shared.observability.domain import (
    InvocationContext,
    LogFormat,
    LogLevel,
    LoggingSettings,
)
from app.shared.observability.sinks import build_diagnostic_handler
from app.shared.tests.resources import ResourceProbe


class TestTransactionLogging:
    @pytest.fixture(
        params=[
            pytest.param("completed", id="committed"),
            pytest.param("failed", id="work-failed"),
            pytest.param("cancelled", id="cancelled"),
            pytest.param("commit", id="commit-failed"),
            pytest.param("rollback", id="rollback-failed"),
            pytest.param("close", id="close-failed-after-commit"),
        ]
    )
    def mode(self, request):
        return request.param

    @pytest.fixture(
        params=[pytest.param(format, id=format.value) for format in LogFormat]
    )
    def format(self, request):
        return request.param

    @pytest.fixture(
        params=[
            pytest.param(level, id=level.name)
            for level in (LogLevel.INFO, LogLevel.DEBUG)
        ]
    )
    def level(self, request):
        return request.param

    @pytest.fixture
    def capture(self, format, level, monkeypatch):
        output = StringIO()
        handler = build_diagnostic_handler(
            LoggingSettings(format=format, level=level), output
        )
        target = logging.getLogger("app.shared.observability")
        monkeypatch.setattr(target, "handlers", [handler])
        monkeypatch.setattr(target, "level", logging.DEBUG)
        monkeypatch.setattr(target, "propagate", False)
        yield output
        handler.close()

    @pytest.fixture
    def context(self):
        return InvocationContext(
            invocation_id="transaction-invocation",
            source="transaction_probe",
            started_ns=0,
        )

    @pytest.fixture
    def primary(self, mode):
        if mode == "cancelled":
            return asyncio.CancelledError("primary_secret")
        return (
            RuntimeError("primary_secret") if mode in ("failed", "rollback") else None
        )

    @pytest.fixture
    def probe(self, mode, monkeypatch):
        failures = (
            {mode: RuntimeError(f"{mode}_secret")}
            if mode in ("commit", "rollback", "close")
            else {}
        )
        probe = ResourceProbe(failures=failures)
        monkeypatch.setattr(database, "connect_database", probe.create_resource)
        return probe

    @pytest.fixture
    def observed(self, probe, primary, capture, context):
        observed = None
        try:
            with database.open_database_transaction(context=context):
                if primary is not None:
                    raise primary
        except BaseException as error:
            observed = error
        return observed

    def test_diagnostic_matches_transaction_outcome(
        self, observed, probe, primary, capture, mode, level
    ):
        expected = primary if primary is not None else probe.failures.get(mode)
        assert observed is expected
        events = [
            json.loads(line.removeprefix("event "))
            for line in capture.getvalue().splitlines()
        ]
        assert {item["invocation_id"] for item in events} <= {"transaction-invocation"}
        assert "secret" not in capture.getvalue()
        if mode == "cancelled" and level is LogLevel.INFO:
            assert events == []
            return
        assert sum(item["event"] == "transaction.started" for item in events) == (
            level is LogLevel.DEBUG
        )
        expected_outcome = (
            "committed"
            if mode in ("completed", "close")
            else "rollback_failed"
            if mode == "rollback"
            else "rolled_back"
        )
        assert events[-1]["event"] == f"transaction.{expected_outcome}"
        assert events[-1]["outcome"] == expected_outcome
        assert not any("exceptions" in item for item in events)
        assert probe.events[-1] == "close"
        if mode == "commit":
            assert probe.events == ["commit", "rollback", "close"]
        if mode == "rollback":
            assert "rollback_secret" in primary.__notes__[0]

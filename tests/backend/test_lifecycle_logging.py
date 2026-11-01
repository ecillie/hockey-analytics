"""Lifespan diagnostics are safe protocol data without changing primary failures."""

import asyncio
import json
import logging

import pytest
from sqlalchemy import create_engine, event

from app.config import AppEnvironment, DatabaseSettings
from app.main import create_app
from app.shared.observability.domain import LogFormat, LoggingSettings
from app.shared.observability.formatting import SafeFormatter
from app.shared.observability.schemas import read_lifecycle_report
from app.shared.observability.policy import LifecycleReportFilter
from app.shared.observability.tests.lifecycle import (
    LifecycleResources,
    LifecycleTransport,
    exercise_lifespan,
)
from app.shared.tests.resources import ResourceProbe
from app.shared.observability.tests.fakes import MetadataAccessError


class TestHostileLifecycleMetadata:
    @pytest.fixture(
        params=[
            pytest.param(RuntimeError, id="metadata-error"),
            pytest.param(asyncio.CancelledError, id="metadata-cancellation"),
            pytest.param(KeyboardInterrupt, id="metadata-interrupt"),
        ]
    )
    def primary(self, request):
        return MetadataAccessError(failure=request.param("metadata_secret"))

    @pytest.fixture
    def scenario(self, primary):
        resources = LifecycleResources(
            engine=create_engine("sqlite://"),
            probe=ResourceProbe(failures={"construct": primary}),
        )
        application = create_app(
            database_settings=DatabaseSettings(
                environment=AppEnvironment.DEV, database_url="sqlite://"
            ),
            resource_factory=resources.create_resources,
        )
        transport = LifecycleTransport(incoming=[{"type": "lifespan.startup"}])
        try:
            yield application, transport
        finally:
            resources.engine.dispose()

    def test_serialization_fault_cannot_replace_primary(self, scenario, primary):
        application, transport = scenario
        with pytest.raises(BaseException) as raised:
            asyncio.run(exercise_lifespan(application, transport))
        assert raised.value is primary
        assert len(transport.outgoing) == 1
        report = read_lifecycle_report(
            logging.LogRecord(
                "uvicorn.error",
                logging.ERROR,
                "",
                1,
                transport.outgoing[0]["message"],
                (),
                None,
            )
        )
        assert report is not None
        assert report.event == "service.startup_failed"
        assert report.exceptions_truncated is True
        assert "secret" not in transport.outgoing[0]["message"]


class TestLifespanFailures:
    @pytest.fixture(
        params=[
            pytest.param("construct", id="startup"),
            pytest.param("dispose", id="shutdown"),
        ]
    )
    def operation(self, request):
        return request.param

    @pytest.fixture(
        params=[
            pytest.param(ValueError, id="failure"),
            pytest.param(asyncio.CancelledError, id="cancellation"),
        ]
    )
    def failure(self, request):
        failure = request.param("connection_secret")
        failure.__cause__ = RuntimeError("cause_secret")
        failure.add_note("cleanup_secret")
        return failure

    @pytest.fixture
    def scenario(self, operation, failure):
        resources = LifecycleResources(
            engine=create_engine("sqlite://"),
            probe=ResourceProbe(failures={operation: failure}),
        )
        event.listen(resources.engine, "engine_disposed", resources.record_disposal)
        application = create_app(
            database_settings=DatabaseSettings(
                environment=AppEnvironment.DEV, database_url="sqlite://"
            ),
            resource_factory=resources.create_resources,
        )
        transport = LifecycleTransport(
            incoming=[{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
        )
        try:
            yield application, transport, resources
        finally:
            event.remove(resources.engine, "engine_disposed", resources.record_disposal)
            resources.engine.dispose()

    @pytest.fixture(
        params=[pytest.param(format, id=format.value) for format in LogFormat]
    )
    def formatter(self, request):
        return SafeFormatter(settings=LoggingSettings(format=request.param))

    def test_protocol_failure_keeps_exception_and_sends_one_safe_diagnostic(
        self, scenario, operation, failure, formatter, caplog
    ):
        application, transport, resources = scenario
        caplog.set_level(logging.INFO)
        with pytest.raises(type(failure)) as raised:
            asyncio.run(exercise_lifespan(application, transport))
        assert raised.value is failure
        assert resources.probe.events == (
            ["construct"] if operation == "construct" else ["construct", "dispose"]
        )
        failures = [
            message
            for message in transport.outgoing
            if message["type"].endswith("failed")
        ]
        assert len(failures) == 1
        assert "secret" not in failures[0]["message"]
        record = logging.LogRecord(
            "uvicorn.error", logging.ERROR, "", 1, failures[0]["message"], (), None
        )
        assert LifecycleReportFilter().filter(record) is True
        payload = json.loads(formatter.format(record).removeprefix("event "))
        phase = "startup" if operation == "construct" else "shutdown"
        cancelled = isinstance(failure, asyncio.CancelledError)
        assert (
            payload["event"]
            == f"service.{phase}_{'cancelled' if cancelled else 'failed'}"
        )
        assert payload["severity"] == (
            "DEBUG" if cancelled else "CRITICAL" if phase == "startup" else "ERROR"
        )
        assert len(payload["exceptions"]) == 2
        assert payload["exceptions"][0]["frames"]
        assert "secret" not in json.dumps(payload)
        assert not any(
            getattr(record, "event", None) == "service.stopped"
            for record in caplog.records
        )
        if operation == "dispose":
            assert application.state.database is None

    @pytest.fixture
    def healthy(self):
        application = create_app()
        transport = LifecycleTransport(
            incoming=[{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
        )
        return application, transport

    def test_successful_lifespan_emits_ready_then_stopped(self, healthy, caplog):
        application, transport = healthy
        caplog.set_level(logging.INFO)
        asyncio.run(exercise_lifespan(application, transport))
        assert [message["type"] for message in transport.outgoing] == [
            "lifespan.startup.complete",
            "lifespan.shutdown.complete",
        ]
        assert [record.event for record in caplog.records] == [
            "service.ready",
            "service.stopped",
        ]


class TestInvalidLifecycleReports:
    @pytest.fixture(
        params=[
            pytest.param(
                'tradevalue.lifecycle {"event":"service.startup_failed","exceptions":[],"exceptions_truncated":false,"password":"secret"}',
                id="unknown-field",
            ),
            pytest.param(
                'tradevalue.lifecycle {"event":"secret","exceptions":[],"exceptions_truncated":false}',
                id="unknown-event",
            ),
            pytest.param(
                'tradevalue.lifecycle {"event":"service.startup_failed","exceptions":[{"type":"secret://url","frames":[],"frames_truncated":false}],"exceptions_truncated":false}',
                id="unsafe-type",
            ),
            pytest.param("tradevalue.lifecycle not-json-secret", id="malformed"),
            pytest.param("tradevalue.lifecycle " + "secret" * 2000, id="oversize"),
        ]
    )
    def record(self, request):
        return logging.LogRecord(
            "uvicorn.error", logging.ERROR, "", 1, request.param, (), None
        )

    def test_invalid_forwarded_payload_is_not_echoed(self, record):
        assert read_lifecycle_report(record) is None
        payload = SafeFormatter().format(record)
        assert json.loads(payload)["event"] == "dependency.record"
        assert "secret" not in payload


class TestPrimaryLifespanFailure:
    @pytest.fixture
    def primary(self):
        return asyncio.CancelledError("primary_secret")

    @pytest.fixture
    def scenario(self, primary):
        resources = LifecycleResources(
            engine=create_engine("sqlite://"),
            probe=ResourceProbe(failures={"dispose": ValueError("cleanup_secret")}),
        )
        event.listen(resources.engine, "engine_disposed", resources.record_disposal)
        application = create_app(
            database_settings=DatabaseSettings(
                environment=AppEnvironment.DEV, database_url="sqlite://"
            ),
            resource_factory=resources.create_resources,
        )
        transport = LifecycleTransport(
            incoming=[{"type": "lifespan.startup"}], receive_failure=primary
        )
        try:
            yield application, transport, resources
        finally:
            event.remove(resources.engine, "engine_disposed", resources.record_disposal)
            resources.engine.dispose()

    def test_cleanup_failure_retains_primary_cancellation_and_safe_protocol(
        self, scenario, primary
    ):
        application, transport, resources = scenario
        with pytest.raises(asyncio.CancelledError) as raised:
            asyncio.run(exercise_lifespan(application, transport))
        assert raised.value is primary
        assert resources.probe.events == ["construct", "dispose"]
        assert application.state.database is None
        assert "cleanup_secret" in "\n".join(primary.__notes__)
        assert transport.outgoing[-1]["type"] == "lifespan.shutdown.failed"
        assert "secret" not in transport.outgoing[-1]["message"]
        record = logging.LogRecord(
            "uvicorn.error",
            logging.ERROR,
            "",
            1,
            transport.outgoing[-1]["message"],
            (),
            None,
        )
        report = read_lifecycle_report(record)
        assert report is not None
        assert report.event == "service.shutdown_failed"
        assert [error.type for error in report.exceptions] == [
            "CancelledError",
            "ValueError",
        ]

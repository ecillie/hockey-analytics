"""Request correlation preserves streaming, cancellation and concurrent isolation."""

import asyncio
import json
import logging

import pytest

from app.shared.observability.formatting import SafeFormatter
from app.shared.observability.policy import ReportedRequestFilter, RequestFailureFilter
from app.shared.observability.domain import RequestFailure, RequestOutcome
from app.shared.observability.requests import get_request_context
from app.shared.observability.tests.requests import (
    RecordingTransport,
    RequestApplication,
    RequestScenario,
    build_request_scope,
    exercise_concurrent_requests,
)


class TestRequestCorrelation:
    @pytest.fixture
    def scenario(self, caplog):
        caplog.set_level(logging.DEBUG, logger="app.shared.observability.requests")
        return RequestScenario(
            application=RequestApplication(transport=RecordingTransport()),
            scope=build_request_scope(),
        )

    def test_request_id_and_streaming_body_are_preserved_without_payload_logs(
        self, scenario, caplog
    ):
        scenario.run()
        messages = scenario.application.transport.messages
        assert [message["body"] for message in messages[1:]] == [
            b"response_secret",
            b"final_chunk",
        ]
        assert scenario.application.delivery_counts == [2]
        assert scenario.application.transport.reads == [True]
        header = dict(messages[0]["headers"])[b"x-request-id"].decode()
        assert len(header) == 32
        context = get_request_context(scenario.scope)
        assert context is not None
        assert context.request_id == header
        assert caplog.records[-1].request_id == header
        assert caplog.records[-1].outcome == "completed"
        assert caplog.records[-1].duration_ms >= 0
        payload = json.loads(SafeFormatter().format(caplog.records[-1]))
        assert payload["route"] == "/api/probe/{key}"
        assert "secret" not in json.dumps(payload)

    @pytest.fixture(
        params=[
            pytest.param(RuntimeError, id="failed-stream"),
            pytest.param(asyncio.CancelledError, id="cancelled-stream"),
        ]
    )
    def failure(self, request):
        return request.param("primary_secret")

    @pytest.fixture
    def failed_scenario(self, failure, caplog):
        caplog.set_level(logging.DEBUG, logger="app.shared.observability.requests")
        return RequestScenario(
            application=RequestApplication(
                transport=RecordingTransport(), failure=failure
            ),
            scope=build_request_scope(),
        )

    def test_stream_failures_and_cancellation_keep_original_exception(
        self, failed_scenario, failure, caplog
    ):
        with pytest.raises(type(failure)) as raised:
            failed_scenario.run()
        assert raised.value is failure
        assert len(failed_scenario.application.transport.messages) == 2
        assert caplog.records[-1].outcome == (
            "cancelled" if isinstance(failure, asyncio.CancelledError) else "failed"
        )
        assert caplog.records[-1].levelno == (
            logging.DEBUG
            if isinstance(failure, asyncio.CancelledError)
            else logging.INFO
        )
        assert all(record.exc_info is None for record in caplog.records)

    def test_propagated_failures_keep_correlation_at_the_host_boundary(
        self, failed_scenario, failure, caplog
    ):
        with pytest.raises(type(failure)):
            failed_scenario.run()
        record = logging.LogRecord(
            "uvicorn.error",
            logging.ERROR,
            "",
            1,
            "Exception in ASGI application\n",
            (),
            (type(failure), failure, failure.__traceback__),
        )
        assert RequestFailureFilter().filter(record) is True
        payload = json.loads(SafeFormatter().format(record))
        assert payload["request_id"] == caplog.records[-1].request_id
        assert payload["status"] == 200
        assert payload["event"] == (
            "request.cancelled"
            if isinstance(failure, asyncio.CancelledError)
            else "request.failed"
        )
        assert payload["severity"] == (
            "DEBUG" if isinstance(failure, asyncio.CancelledError) else "ERROR"
        )
        assert record.levelno == (
            logging.DEBUG
            if isinstance(failure, asyncio.CancelledError)
            else logging.ERROR
        )
        assert "secret" not in json.dumps(payload)

    @pytest.fixture(
        params=[pytest.param(200, id="healthy"), pytest.param(503, id="unhealthy")]
    )
    def health_scenario(self, request, caplog):
        caplog.set_level(logging.INFO, logger="app.shared.observability.requests")
        return RequestScenario(
            application=RequestApplication(
                transport=RecordingTransport(),
                status=request.param,
                route_path="/api/health",
            ),
            scope=build_request_scope(path="/api/health"),
        )

    def test_successful_health_probes_are_quiet_but_failures_are_retained(
        self, health_scenario, caplog
    ):
        health_scenario.run()
        assert len(caplog.records) == (
            0 if health_scenario.application.status == 200 else 1
        )


class TestConcurrentRequestContext:
    @pytest.fixture
    def scenario(self, caplog):
        caplog.set_level(logging.INFO, logger="app.shared.observability.requests")
        shared_state = {"existing": "preserved"}
        scopes = (build_request_scope(), build_request_scope())
        for scope in scopes:
            scope["state"] = shared_state
        transports = (RecordingTransport(), RecordingTransport())
        application = RequestApplication(transport=transports[0])
        return application, scopes, transports, shared_state

    def test_interleaved_requests_get_distinct_contexts_without_mutating_shared_state(
        self, scenario, caplog
    ):
        application, scopes, transports, shared_state = scenario
        asyncio.run(exercise_concurrent_requests(application, scopes, transports))
        ids = {
            dict(transport.messages[0]["headers"])[b"x-request-id"].decode()
            for transport in transports
        }
        assert len(ids) == 2
        assert {record.request_id for record in caplog.records} == ids
        assert {
            context.request_id
            for scope in scopes
            if (context := get_request_context(scope)) is not None
        } == ids
        assert shared_state == {"existing": "preserved"}


class TestReportedHostDuplicates:
    @pytest.fixture
    def record(self):
        error = RuntimeError("primary_secret")
        error.__dict__["tradevalue_request"] = RequestFailure(
            request_id="generated-id",
            method="GET",
            route="/api/probe",
            status=500,
            duration_ms=1.0,
            outcome=RequestOutcome.FAILED,
            reported=True,
        )
        return logging.LogRecord(
            "uvicorn.error",
            logging.ERROR,
            "",
            1,
            "Exception in ASGI application\n",
            (),
            (RuntimeError, error, None),
        )

    def test_matching_report_is_consumed_once_without_hiding_a_later_host_error(
        self, record
    ):
        assert ReportedRequestFilter().filter(record) is False
        assert ReportedRequestFilter().filter(record) is True

    def test_unrelated_host_record_does_not_consume_the_pending_report(self, record):
        record.msg = "Unrelated host failure"
        assert ReportedRequestFilter().filter(record) is True
        record.msg = "Exception in ASGI application\n"
        assert ReportedRequestFilter().filter(record) is False

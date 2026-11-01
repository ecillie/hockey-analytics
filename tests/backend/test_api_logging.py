"""HTTP correlation, outer CORS and failure ownership on the application stack."""

from collections.abc import Generator
from dataclasses import replace
import logging
import json
import os
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.exc import OperationalError
from starlette.routing import Route

from app.api.routes import get_service
from app.main import create_app
from app.shared.observability.domain import LogLevel
from app.shared.observability.formatting import SafeFormatter
from app.shared.observability.tests.requests import (
    RecordingTransport,
    RequestApplication,
    parse_probe_number,
)
from app.shared.observability.tests.fakes import capture_source_failure


class TestObservedApi:
    @pytest.fixture(
        params=[
            pytest.param(level, id=level.name)
            for level in (LogLevel.INFO, LogLevel.DEBUG)
        ]
    )
    def level(self, request):
        return request.param

    @pytest.fixture(
        params=[
            pytest.param("success", id="success"),
            pytest.param("invalid", id="invalid"),
            pytest.param("missing", id="missing"),
            pytest.param("database", id="database"),
            pytest.param("unexpected", id="unexpected"),
            pytest.param("unconfigured", id="unconfigured"),
        ]
    )
    def case(self, request):
        return request.param

    @pytest.fixture
    def observed(self, service, case, level, caplog) -> Generator:
        application = create_app()
        application.add_api_route("/numbers/{key}", parse_probe_number)
        selected = replace(
            service,
            repository=replace(
                service.repository,
                health_failure=OperationalError(
                    "SELECT secret", {"secret": "secret"}, ConnectionError("secret")
                )
                if case == "database"
                else None,
            ),
        )

        def provide_service():
            return selected

        if case != "unconfigured":
            application.dependency_overrides[get_service] = provide_service
        caplog.set_level(level)
        paths = {
            "success": "/api/seasons?token=secret",
            "invalid": "/api/players?season=bad_secret",
            "missing": "/missing_secret?token=secret",
            "database": "/api/health?token=secret",
            "unexpected": "/numbers/value_secret",
            "unconfigured": "/api/health",
        }
        with TestClient(application, raise_server_exceptions=False) as client:
            response = client.get(
                paths[case],
                headers={
                    "Origin": "http://localhost:5173",
                    "X-Request-ID": "caller_secret",
                },
            )
            yield response, application, tuple(caplog.records)

    def test_all_response_paths_have_correlated_safe_summaries(self, observed, case):
        response, application, records = observed
        assert (
            response.status_code
            == {
                "success": 200,
                "invalid": 400,
                "missing": 404,
                "database": 503,
                "unexpected": 500,
                "unconfigured": 503,
            }[case]
        )
        assert application.debug is False
        request_id = response.headers["x-request-id"]
        assert len(request_id) == 32
        assert request_id != "caller_secret"
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:5173"
        )
        assert response.headers["access-control-expose-headers"] == "X-Request-ID"
        summaries = [
            record
            for record in records
            if getattr(record, "event", None) == "request.finished"
        ]
        errors = [
            record
            for record in records
            if getattr(record, "event", None) == "request.failed"
        ]
        assert len(summaries) == 1
        assert summaries[0].request_id == request_id
        assert summaries[0].status == response.status_code
        assert len(errors) == (
            1 if case in ("database", "unexpected", "unconfigured") else 0
        )
        assert all(record.request_id == request_id for record in errors)
        assert "secret" not in "\n".join(
            SafeFormatter().format(record) for record in summaries + errors
        )
        if case == "unexpected":
            assert response.json() == {
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "The API could not complete this request.",
                }
            }

    @pytest.fixture
    def disallowed_origin_response(self):
        application = create_app()
        with TestClient(application) as client:
            return client.get(
                "/unknown", headers={"Origin": "https://untrusted.invalid"}
            )

    def test_disallowed_origins_remain_disallowed(self, disallowed_origin_response):
        assert "access-control-allow-origin" not in disallowed_origin_response.headers
        assert "x-request-id" in disallowed_origin_response.headers


class TestObservedStreamingFailure:
    @pytest.fixture
    def failure(self):
        return capture_source_failure()

    @pytest.fixture
    def application(self, failure):
        application = create_app()
        application.router.routes.append(
            Route(
                "/stream",
                endpoint=RequestApplication(
                    transport=RecordingTransport(), failure=failure
                ),
            )
        )
        return application

    def test_failure_after_headers_keeps_original_exception_and_reports_once(
        self, application, failure, caplog
    ):
        caplog.set_level(logging.INFO)
        with TestClient(application) as client:
            with pytest.raises(ValueError) as raised:
                client.get("/stream")
        assert raised.value is failure
        errors = [
            record
            for record in caplog.records
            if getattr(record, "event", None) == "request.failed"
        ]
        summaries = [
            record
            for record in caplog.records
            if getattr(record, "event", None) == "request.finished"
        ]
        assert len(errors) == len(summaries) == 1
        assert errors[0].request_id == summaries[0].request_id
        assert summaries[0].status == 200
        assert summaries[0].outcome == "failed"
        assert errors[0].exc_info[1] is failure


class TestHostDiagnostics:
    script = """
import asyncio
import json
import logging
import os
from io import StringIO
import httpx
from app.main import create_app
from app.shared.observability.domain import read_logging_settings
from app.shared.observability.services import configure_logging, configure_api_host_logging
from app.shared.observability.lifecycle import serialize_lifecycle_failure
from app.shared.observability.tests.requests import parse_probe_number

async def exercise(application):
    async with asyncio.timeout(10):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://probe") as client:
            try:
                await client.get("/numbers/primary_secret?token=query_secret", headers={"X-Request-ID": "caller_secret"})
            except ValueError as error:
                return error
    raise AssertionError("request must preserve its failure")

def main():
    root_capture = StringIO()
    logging.getLogger().addHandler(logging.StreamHandler(root_capture))
    host_capture = StringIO()
    host_handler = logging.StreamHandler(host_capture)
    logging.getLogger("uvicorn").addHandler(host_handler)
    application_capture = StringIO()
    settings = read_logging_settings(os.environ)
    handler = configure_logging(settings, stream=application_capture)
    configure_api_host_logging(settings, handler)
    configure_api_host_logging(settings, handler)
    assert logging.getLogger("uvicorn").handlers == [host_handler]
    assert len(logging.getLogger("uvicorn.error").filters) == 3
    application = create_app()
    application.add_api_route("/numbers/{key}", parse_probe_number)
    error = asyncio.run(exercise(application))
    assert error.__dict__["tradevalue_request"].reported is True
    logging.getLogger("uvicorn.error").error("Exception in ASGI application\\n", exc_info=error)
    logging.getLogger("uvicorn.error").error("unrelated_host_secret", exc_info=error)
    logging.getLogger("uvicorn.error").error(serialize_lifecycle_failure(error, "startup", settings))
    logging.getLogger("other.host").warning("host preserved")
    def parse_lines(stream):
        return [json.loads(line.removeprefix("event ")) for line in stream.getvalue().splitlines()]
    print(json.dumps({"app": parse_lines(application_capture), "host": parse_lines(host_capture), "root": root_capture.getvalue(), "access": logging.getLogger("uvicorn.access").disabled}))
    return 0

raise SystemExit(main())
"""

    @pytest.fixture(
        params=[
            pytest.param("INFO", id="normal"),
            pytest.param("DEBUG", id="debug"),
            pytest.param("CRITICAL", id="critical"),
        ]
    )
    def threshold(self, request):
        return request.param

    @pytest.fixture(
        params=[pytest.param("json", id="json"), pytest.param("text", id="text")]
    )
    def format(self, request):
        return request.param

    @pytest.fixture
    def completed(self, threshold, format):
        environment = dict(os.environ) | {"LOG_LEVEL": threshold, "LOG_FORMAT": format}
        return subprocess.run(
            [sys.executable, "-c", self.script],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_api_diagnostics_are_single_safe_streams_and_host_errors_are_preserved(
        self, completed, threshold
    ):
        assert completed.returncode == 0, completed.stderr
        assert completed.stderr == ""
        result = json.loads(completed.stdout)
        assert "secret" not in completed.stdout
        assert result["root"] == "host preserved\n"
        assert result["access"] is True
        expected = (
            []
            if threshold == "CRITICAL"
            else (["request.started"] if threshold == "DEBUG" else [])
            + ["request.failed", "request.finished"]
        )
        assert [item["event"] for item in result["app"]] == expected
        assert [item["event"] for item in result["host"]] == (
            [] if threshold == "CRITICAL" else ["dependency.record"]
        ) + ["service.startup_failed"]
        assert result["host"][-1]["severity"] == "CRITICAL"


class TestPreflightAndMethodResponses:
    @pytest.fixture(
        params=[
            pytest.param("OPTIONS", id="preflight"),
            pytest.param("POST", id="method-not-allowed"),
        ]
    )
    def method(self, request):
        return request.param

    @pytest.fixture
    def observed(self, method, caplog):
        caplog.set_level(logging.INFO)
        with TestClient(create_app()) as client:
            response = client.request(
                method,
                "/api/health",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "GET",
                },
            )
            return response, tuple(caplog.records)

    def test_preflight_and_rejected_methods_keep_headers_and_summaries(
        self, observed, method
    ):
        response, records = observed
        assert response.status_code == (200 if method == "OPTIONS" else 405)
        assert len(response.headers["x-request-id"]) == 32
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:5173"
        )
        summaries = [
            record
            for record in records
            if getattr(record, "event", None) == "request.finished"
        ]
        assert len(summaries) == 1
        assert summaries[0].method == method
        assert summaries[0].request_id == response.headers["x-request-id"]
        if method == "POST":
            assert response.json() == {"detail": "Method Not Allowed"}

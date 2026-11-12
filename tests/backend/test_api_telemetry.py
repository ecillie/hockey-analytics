"""Application Insights export: disabled by default, allowlisted fields when enabled."""

from collections.abc import Generator
from dataclasses import dataclass
import json
import logging

from fastapi.testclient import TestClient
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
import pytest

from app.api.routes import get_service
from app.main import create_app
from app.shared.observability.domain import (
    LoggingSettings,
    TelemetrySettings,
    read_telemetry_settings,
)
from app.shared.observability.errors import TelemetrySettingsError
from app.shared.observability.telemetry import (
    TELEMETRY_HANDLER_NAME,
    TelemetryExporters,
    TelemetryHandler,
    build_azure_exporters,
)
from app.shared.observability.tests.requests import parse_probe_number


CONNECTION_STRING = (
    "InstrumentationKey=00000000-0000-0000-0000-000000000000;"
    "IngestionEndpoint=https://eastus-8.in.applicationinsights.azure.com/"
)


@dataclass(slots=True, kw_only=True, frozen=True)
class Exported:
    application: object
    spans: InMemorySpanExporter
    logs: InMemoryLogRecordExporter

    def flush(self) -> None:
        handler = logging.getHandlerByName(TELEMETRY_HANDLER_NAME)
        assert isinstance(handler, TelemetryHandler)
        handler.flush()
        handler.tracer_provider.force_flush()
        handler.logger_provider.force_flush()

    def text(self) -> str:
        spans = [span.to_json() for span in self.spans.get_finished_spans()]
        logs = [item.to_json() for item in self.logs.get_finished_logs()]
        return json.dumps(spans + logs)


@pytest.fixture
def isolate_host_logging(monkeypatch, isolate_command_logging):
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        target = logging.getLogger(name)
        for attribute in ("handlers", "filters"):
            monkeypatch.setattr(target, attribute, list(getattr(target, attribute)))
        for attribute in ("level", "propagate", "disabled"):
            monkeypatch.setattr(target, attribute, getattr(target, attribute))
    yield
    handler = logging.getHandlerByName(TELEMETRY_HANDLER_NAME)
    if isinstance(handler, TelemetryHandler):
        handler.shutdown()


def build_application(service, telemetry_settings, exporters=None):
    application = create_app(
        logging_settings=LoggingSettings(environment="prod"),
        telemetry_settings=telemetry_settings,
        telemetry_exporters=exporters,
    )
    application.add_api_route("/numbers/{key}", parse_probe_number)

    def provide_service():
        return service

    application.dependency_overrides[get_service] = provide_service
    return application


class TestTelemetrySettings:
    def test_missing_or_blank_connection_string_disables_export(self):
        assert not read_telemetry_settings({}).enabled
        assert not read_telemetry_settings(
            {"APPLICATIONINSIGHTS_CONNECTION_STRING": "  "}
        ).enabled

    def test_connection_string_is_kept_out_of_repr(self):
        settings = read_telemetry_settings(
            {"APPLICATIONINSIGHTS_CONNECTION_STRING": CONNECTION_STRING}
        )
        assert settings.enabled
        assert "InstrumentationKey" not in repr(settings)

    def test_connection_string_without_key_is_rejected_without_echoing_it(self):
        with pytest.raises(TelemetrySettingsError) as raised:
            read_telemetry_settings(
                {"APPLICATIONINSIGHTS_CONNECTION_STRING": "Endpoint=secret_value"}
            )
        assert "secret_value" not in str(raised.value)

    def test_azure_exporters_build_from_connection_string(self):
        exporters = build_azure_exporters(
            TelemetrySettings(connection_string=CONNECTION_STRING)
        )
        try:
            assert type(exporters.spans).__name__ == "AzureMonitorTraceExporter"
            assert type(exporters.logs).__name__ == "AzureMonitorLogExporter"
        finally:
            exporters.spans.shutdown()
            exporters.logs.shutdown()


@pytest.mark.usefixtures("isolate_host_logging")
class TestTelemetryDisabled:
    def test_startup_and_requests_are_unchanged(self, service):
        application = build_application(service, TelemetrySettings())
        with TestClient(application) as client:
            assert client.get("/api/seasons").status_code == 200
        assert logging.getHandlerByName(TELEMETRY_HANDLER_NAME) is None
        assert application.state.request_telemetry.tracer is None


@pytest.mark.usefixtures("isolate_host_logging")
class TestTelemetryEnabled:
    @pytest.fixture
    def exported(self, service) -> Generator[Exported]:
        spans, logs = InMemorySpanExporter(), InMemoryLogRecordExporter()
        application = build_application(
            service,
            TelemetrySettings(connection_string=CONNECTION_STRING),
            TelemetryExporters(spans=spans, logs=logs),
        )
        yield Exported(application=application, spans=spans, logs=logs)

    def test_request_becomes_server_span_with_route_template(self, exported):
        with TestClient(exported.application) as client:
            response = client.get("/api/seasons?q=secret_search_term")
        exported.flush()
        (span,) = exported.spans.get_finished_spans()
        assert span.name == "GET /api/seasons"
        assert span.attributes["http.route"] == "/api/seasons"
        assert span.attributes["http.response.status_code"] == 200
        assert span.attributes["request_id"] == response.headers["x-request-id"]
        assert span.status.status_code is StatusCode.OK
        assert "secret_search_term" not in exported.text()

    def test_logs_are_exported_and_correlated_with_the_request(self, exported):
        with TestClient(exported.application) as client:
            client.get("/api/seasons")
        exported.flush()
        (span,) = exported.spans.get_finished_spans()
        finished = [
            item.log_record
            for item in exported.logs.get_finished_logs()
            if item.log_record.attributes["event"] == "request.finished"
        ]
        assert len(finished) == 1
        assert finished[0].attributes["environment"] == "prod"
        assert finished[0].trace_id == span.context.trace_id
        events = {
            item.log_record.attributes["event"]
            for item in exported.logs.get_finished_logs()
        }
        assert "service.ready" in events

    def test_exception_exports_type_and_frames_but_not_its_value(self, exported):
        with TestClient(exported.application, raise_server_exceptions=False) as client:
            assert client.get("/numbers/value_secret").status_code == 500
        exported.flush()
        (span,) = exported.spans.get_finished_spans()
        assert span.status.status_code is StatusCode.ERROR
        (failure,) = [
            item.log_record
            for item in exported.logs.get_finished_logs()
            if item.log_record.attributes["event"] == "request.failed"
        ]
        assert failure.attributes["exception.type"] == "ValueError"
        assert "exception.message" not in failure.attributes
        assert " at " in failure.attributes["exception.stacktrace"]
        assert failure.trace_id == span.context.trace_id
        assert "value_secret" not in exported.text()

    def test_successful_health_probe_is_not_exported_at_info(self, exported):
        with TestClient(exported.application) as client:
            assert client.get("/api/health").status_code == 200
        exported.flush()
        assert exported.spans.get_finished_spans() == ()

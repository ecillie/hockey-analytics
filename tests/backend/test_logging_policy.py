"""Settings and adversarial output behavior without global handler mutation."""

import asyncio
import json
import logging
import os
import subprocess
import sys
from contextlib import ExitStack
from io import StringIO
from pathlib import Path
import httpx

from hypothesis import given
import pytest

from app.shared.observability import formatting, services
from app.shared.observability.domain import (
    LogFormat,
    LogLevel,
    LoggingSettings,
    LoggingSettingsError,
    read_logging_settings,
    RecordLimits,
)
from app.shared.observability.formatting import SafeFormatter
from app.shared.observability.tests.fakes import (
    EnvironmentLogObservation,
    LogCaptureScenario,
    BrokenStream,
    HostileValue,
    build_exception_record,
    build_bounded_record,
    build_connection_error_record,
    build_http_error_record,
    MetadataAccessError,
    generate_formatting_scenarios,
)
from app.shared.observability.tests import verify_http, verify_logs
from app.shared.observability.sinks import build_diagnostic_handler
from app.shared.observability.policy import RecordLimitsError
from pydantic import TypeAdapter, ValidationError


class TestEnvironmentLogDelivery:
    @pytest.fixture(
        params=[
            pytest.param(("dev", True), id="dev-enabled"),
            pytest.param((" NONPROD ", False), id="nonprod-disabled"),
            pytest.param((" PROD ", False), id="prod-disabled"),
        ]
    )
    def environment_case(self, request):
        return request.param

    @pytest.fixture(params=[pytest.param(value, id=value.value) for value in LogFormat])
    def log_format(self, request):
        return request.param

    @pytest.fixture
    def observation(
        self, environment_case, log_format, isolate_command_logging, monkeypatch
    ):
        environment, enabled = environment_case
        with ExitStack() as cleanup:
            application_output = cleanup.enter_context(StringIO())
            host_output = cleanup.enter_context(StringIO())
            native_handler = logging.StreamHandler(host_output)
            cleanup.callback(native_handler.close)
            host = logging.getLogger("uvicorn")
            errors = logging.getLogger("uvicorn.error")
            for target in (host, errors):
                monkeypatch.setattr(target, "handlers", [])
                monkeypatch.setattr(target, "filters", [])
                monkeypatch.setattr(target, "level", logging.NOTSET)
                monkeypatch.setattr(target, "propagate", False)
            monkeypatch.setattr(host, "handlers", [native_handler])
            monkeypatch.setattr(logging.getLogger("uvicorn.access"), "disabled", False)
            settings = read_logging_settings(
                {
                    "ENV": environment,
                    "LOG_LEVEL": "DEBUG",
                    "LOG_FORMAT": log_format.value,
                }
            )
            handler = services.configure_logging(settings, stream=application_output)
            services.configure_api_host_logging(settings, handler)
            services.configure_api_host_logging(settings, handler)
            for level in LogLevel:
                for target in (logging.getLogger("app.environment_probe"), errors):
                    target.log(
                        level, "Environment probe", extra={"event": "command.started"}
                    )
            return EnvironmentLogObservation(
                enabled=enabled,
                application=tuple(application_output.getvalue().splitlines()),
                host=tuple(host_output.getvalue().splitlines()),
            )

    def test_application_and_existing_host_handlers_honor_environment(
        self, observation
    ):
        expected = len(LogLevel) if observation.enabled else 0
        assert len(observation.application) == expected
        assert len(observation.host) == expected


class TestImmutableDiagnosticSnapshots:
    @pytest.fixture
    def snapshot(self):
        info = build_bounded_record().exc_info
        assert isinstance(info, tuple) and info[1] is not None
        return formatting.collect_exceptions(info[1], RecordLimits())

    def test_exception_and_frame_snapshots_reject_mutation(self, snapshot):
        with pytest.raises(ValidationError, match="frozen"):
            snapshot.items[0].type = "Changed"
        with pytest.raises(ValidationError, match="frozen"):
            snapshot.items[0].frames[0].module = "Changed"

    def test_serialized_mutation_cannot_change_retained_snapshot(self, snapshot):
        payload = snapshot.items[0].model_dump()
        payload["frames"][0]["module"] = "Changed"
        assert snapshot.items[0].frames[0].module != "Changed"


class TestHostileFailureMetadata:
    @pytest.fixture
    def formatter(self):
        return SafeFormatter()

    @pytest.fixture(
        params=[
            pytest.param(RuntimeError, id="metadata-error"),
            pytest.param(asyncio.CancelledError, id="metadata-cancellation"),
            pytest.param(KeyboardInterrupt, id="metadata-interrupt"),
        ]
    )
    def record(self, request):
        primary = MetadataAccessError(failure=request.param("metadata_secret"))
        record = build_exception_record("payload_secret")
        record.exc_info = (type(primary), primary, None)
        return record

    def test_metadata_fault_does_not_escape_diagnostic_rendering(
        self, record, formatter
    ):
        try:
            rendered = formatter.format(record)
        except BaseException as failure:
            assert False, f"metadata fault escaped: {type(failure).__name__}"
        payload = json.loads(rendered)
        assert payload["exceptions_truncated"] is True
        assert payload["exceptions"][0]["type"] == "MetadataAccessError"
        assert "secret" not in json.dumps(payload)


class TestLoggingSettings:
    @pytest.fixture
    def defaults(self):
        return read_logging_settings({})

    def test_defaults_without_database(self, defaults):
        assert defaults.level is LogLevel.INFO
        assert defaults.format is LogFormat.JSON
        assert defaults.environment is None

    @pytest.fixture(params=[pytest.param(level, id=level.name) for level in LogLevel])
    def selected_level(self, request):
        return request.param

    @pytest.fixture
    def selected_values(self, selected_level):
        return {"LOG_LEVEL": f" {selected_level.name.lower()} "}

    def test_levels_are_normalized(self, selected_level, selected_values):
        assert read_logging_settings(selected_values).level is selected_level

    @pytest.fixture(
        params=[
            pytest.param((("LOG_LEVEL", ""),), id="empty-level"),
            pytest.param((("LOG_LEVEL", "warn"),), id="alias-rejected"),
            pytest.param((("LOG_LEVEL", "secret\nvalue"),), id="unsafe-level"),
            pytest.param((("LOG_FORMAT", ""),), id="empty-format"),
            pytest.param((("LOG_FORMAT", "xml"),), id="unknown-format"),
        ]
    )
    def invalid_values(self, request):
        return dict(request.param)

    def test_invalid_values_do_not_echo_input(self, invalid_values):
        with pytest.raises(LoggingSettingsError) as raised:
            read_logging_settings(invalid_values)
        assert "secret" not in str(raised.value)


class TestSafeFormatter:
    @pytest.fixture(
        params=[pytest.param(format, id=format.value) for format in LogFormat]
    )
    def formatter(self, request):
        return SafeFormatter(settings=LoggingSettings(format=request.param))

    @pytest.fixture
    def hostile_record(self):
        record = logging.LogRecord(
            "app.jobs",
            logging.ERROR,
            "/secret/path",
            1,
            HostileValue(),
            (HostileValue(),),
            None,
        )
        record.event = "job.failed"
        record.request_id = "generated-id"
        record.authorization = {"nested": HostileValue()}
        record.duration_ms = 4.5
        record.source = HostileValue()
        return record

    def test_unknown_fields_and_objects_are_not_evaluated(
        self, formatter, hostile_record
    ):
        rendered = formatter.format(hostile_record)
        assert "job.failed" in rendered
        assert "generated-id" in rendered
        assert "authorization" not in rendered
        assert "secret/path" not in rendered
        assert '"source":"unsupported"' in rendered
        assert '"duration_ms":4.5' in rendered

    @given(scenario=generate_formatting_scenarios())
    def test_messages_and_nested_exception_values_are_never_serialized(self, scenario):
        rendered = scenario.formatter.format(scenario.record)
        payload = json.loads(rendered.removeprefix("event "))
        assert payload["message"] == "job failed"
        assert payload["exceptions"] == [
            {"type": "RuntimeError", "frames": [], "frames_truncated": False},
            {"type": "ValueError", "frames": [], "frames_truncated": False},
        ]
        assert len(rendered.encode()) <= 8192
        assert "\n" not in rendered

    def test_corrupt_record_uses_safe_fallback(self, formatter, hostile_record):
        hostile_record.created = float("nan")
        assert "logging.format_failed" in formatter.format(hostile_record)


class TestEmergencyDiagnostics:
    @pytest.fixture(
        params=[pytest.param(format, id=format.value) for format in LogFormat]
    )
    def settings(self, request):
        return LoggingSettings(format=request.param, level=LogLevel.CRITICAL)

    @pytest.fixture(
        params=[
            pytest.param("encode_diagnostic", id="encoder-failure"),
            pytest.param("datetime", id="clock-failure"),
        ]
    )
    def failed_dependency(self, request, monkeypatch):
        monkeypatch.setattr(formatting, request.param, None)
        return request.param

    @pytest.fixture
    def record(self):
        record = build_exception_record("secret")
        record.levelno = logging.CRITICAL
        return record

    @pytest.fixture
    def broken_handler(self, settings):
        return build_diagnostic_handler(settings, BrokenStream())

    def test_formatter_remains_safe_without_encoder_or_clock(
        self, settings, failed_dependency, record
    ):
        rendered = SafeFormatter(settings=settings).format(record)
        payload = json.loads(rendered.removeprefix("event "))
        assert payload["event"] == "logging.format_failed"
        assert payload["severity"] == "CRITICAL"
        assert payload["timestamp_unavailable"] == (failed_dependency == "datetime")
        assert "secret" not in rendered
        assert len(rendered.encode()) < 8192

    def test_failed_sink_never_dumps_raw_record(
        self, broken_handler, failed_dependency, record, capsys
    ):
        broken_handler.handle(record)
        assert capsys.readouterr().err == ""


class TestSafeDelivery:
    @pytest.fixture(params=[pytest.param(level, id=level.name) for level in LogLevel])
    def threshold(self, request):
        return request.param

    @pytest.fixture
    def capture(self):
        return StringIO()

    @pytest.fixture
    def threshold_handler(self, capture, threshold):
        return build_diagnostic_handler(LoggingSettings(level=threshold), capture)

    @pytest.fixture
    def diagnostic_logger(self, threshold_handler, monkeypatch):
        logger = logging.getLogger("isolated.diagnostic")
        monkeypatch.setattr(logger, "level", logging.DEBUG)
        monkeypatch.setattr(logger, "handlers", [threshold_handler])
        monkeypatch.setattr(logger, "propagate", False)
        return logger

    def test_threshold_filters_all_five_severities(
        self, diagnostic_logger, capture, threshold
    ):
        for level in LogLevel:
            diagnostic_logger.log(level, "secret")
        assert [
            json.loads(line)["severity"] for line in capture.getvalue().splitlines()
        ] == [level.name for level in LogLevel if level >= threshold]
        assert "secret" not in capture.getvalue()

    @pytest.fixture
    def broken_handler(self):
        return build_diagnostic_handler(LoggingSettings(), BrokenStream())

    @pytest.fixture
    def record(self):
        return build_exception_record("secret")

    def test_broken_sink_preserves_result(self, broken_handler, record, capsys):
        broken_handler.handle(record)
        assert capsys.readouterr().err == ""


class TestDiagnosticBounds:
    @pytest.fixture(
        params=[pytest.param(format, id=format.value) for format in LogFormat]
    )
    def formatter(self, request):
        return SafeFormatter(
            settings=LoggingSettings(
                format=request.param,
                limits=RecordLimits(
                    record_bytes=1024, stack_frames=1, exception_depth=8
                ),
            )
        )

    @pytest.fixture
    def record(self):
        return build_bounded_record()

    def test_records_fit_ceiling_and_keep_correlation(self, formatter, record):
        rendered = formatter.format(record)
        payload = json.loads(rendered.removeprefix("event "))
        assert len(rendered.encode()) + 1 <= 1024
        assert payload["truncated"] is True
        assert payload["request_id"] == "retained-request-id"
        assert payload["event"] == "job.failed"
        assert "secret" not in rendered
        assert "sensitive source value" not in rendered

    @pytest.fixture
    def full_formatter(self):
        return SafeFormatter()

    def test_stacks_retain_safe_locations_and_mark_chain_limit(
        self, full_formatter, record
    ):
        payload = json.loads(full_formatter.format(record))
        assert payload["exceptions_truncated"] is True
        assert len(payload["exceptions"]) == 4
        assert all(
            error["frames"][0]["module"].endswith("tests.fakes")
            for error in payload["exceptions"]
        )
        assert all(
            frame["line"] > 0
            for error in payload["exceptions"]
            for frame in error["frames"]
        )
        assert "sensitive source value" not in json.dumps(payload)

    @pytest.fixture
    def one_frame_formatter(self):
        return SafeFormatter(
            settings=LoggingSettings(limits=RecordLimits(stack_frames=1))
        )

    def test_frame_limit_is_explicit(self, one_frame_formatter, record):
        payload = json.loads(one_frame_formatter.format(record))
        assert all(error["frames_truncated"] is True for error in payload["exceptions"])
        assert all(len(error["frames"]) == 1 for error in payload["exceptions"])

    @pytest.fixture(
        params=[
            pytest.param(RecordLimits(record_bytes=1), id="record-too-small"),
            pytest.param(RecordLimits(record_bytes=8193), id="record-too-large"),
            pytest.param(RecordLimits(string_characters=0), id="string-too-small"),
            pytest.param(RecordLimits(string_characters=257), id="string-too-large"),
            pytest.param(RecordLimits(stack_frames=0), id="no-frames"),
            pytest.param(RecordLimits(stack_frames=65), id="too-many-frames"),
            pytest.param(RecordLimits(exception_depth=0), id="no-chain"),
            pytest.param(RecordLimits(exception_depth=9), id="too-deep-chain"),
        ]
    )
    def invalid_settings(self, request):
        return LoggingSettings(limits=request.param)

    def test_invalid_limits_fail_before_installation(self, invalid_settings):
        with pytest.raises(RecordLimitsError):
            build_diagnostic_handler(invalid_settings, StringIO())

    @pytest.fixture(
        params=[
            pytest.param(("line\ncontrol", "invalid"), id="control-character"),
            pytest.param(("x" * 257, "truncated"), id="oversize"),
            pytest.param((HostileValue(), "unsupported"), id="object"),
        ]
    )
    def unsafe_identifier(self, request):
        return request.param

    def test_context_strings_are_bounded(
        self, full_formatter, record, unsafe_identifier
    ):
        record.source = unsafe_identifier[0]
        payload = json.loads(full_formatter.format(record))
        assert payload["source"] == unsafe_identifier[1]

    @pytest.fixture
    def metadata_formatter(self):
        return SafeFormatter(
            settings=LoggingSettings(environment="prod", release="a" * 40)
        )

    def test_known_metadata_is_retained(self, metadata_formatter, record):
        payload = json.loads(metadata_formatter.format(record))
        assert payload["environment"] == "prod"
        assert payload["release"] == "a" * 40

    @pytest.fixture
    def unsafe_metadata_formatter(self):
        return SafeFormatter(
            settings=LoggingSettings(
                environment="secret\nENV", release="secret-release"
            )
        )

    def test_programmatic_metadata_is_validated(
        self, unsafe_metadata_formatter, record
    ):
        payload = json.loads(unsafe_metadata_formatter.format(record))
        assert "environment" not in payload
        assert "release" not in payload

    def test_exception_cycle_is_bounded(self, full_formatter, record):
        record.exc_info[1].__cause__ = record.exc_info[1]
        payload = json.loads(full_formatter.format(record))
        assert len(payload["exceptions"]) == 1
        assert payload["exceptions_truncated"] is True

    def test_unsupported_severity_has_safe_fallback(self, full_formatter, record):
        record.levelno = 1234
        assert (
            json.loads(full_formatter.format(record))["event"]
            == "logging.format_failed"
        )


class TestImportIsolation:
    script = """
import logging
import os
import sys

before_environment = dict(os.environ)
before_handlers = tuple(logging.getLogger().handlers)
before_level = logging.getLogger().level
from app.shared.observability.domain import read_logging_settings
from app.shared.observability.formatting import SafeFormatter
from app.shared.observability.sinks import build_diagnostic_handler
from app.shared.observability.policy import find_record_limits_violation
from app.shared.observability.services import configure_logging

assert read_logging_settings({}).level.name == "INFO"
assert tuple(logging.getLogger().handlers) == before_handlers
assert logging.getLogger().level == before_level
assert dict(os.environ) == before_environment
assert "sqlalchemy" not in sys.modules
assert "dotenv" not in sys.modules
"""

    @pytest.fixture
    def clean_environment(self):
        environment = dict(os.environ)
        for key in (
            "DATABASE_URL",
            "DEV_DATABASE_URL",
            "TEST_DATABASE_URL",
            "ENV",
            "PYTHONPATH",
        ):
            environment.pop(key, None)
        environment["TRADEVALUE_ENV_FILE"] = os.devnull
        return environment

    def test_imports_are_silent_and_do_not_configure_logging(self, clean_environment):
        completed = subprocess.run(
            [sys.executable, "-c", self.script],
            env=clean_environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout == ""
        assert completed.stderr == ""


class TestDependencyRecords:
    @pytest.fixture
    def record(self):
        record = build_exception_record("secret URL and SQL parameters")
        record.name = "sqlalchemy.engine"
        record.event = "secret"
        record.request_id = "secret"
        record.source = "secret"
        return record

    @pytest.fixture
    def formatter(self):
        return SafeFormatter()

    def test_dependency_extras_are_not_treated_as_application_context(
        self, formatter, record
    ):
        payload = json.loads(formatter.format(record))
        assert payload["event"] == "dependency.record"
        assert "request_id" not in payload
        assert "source" not in payload
        assert "secret" not in json.dumps(payload)

    def test_digit_leading_request_ids_are_preserved(self, formatter, record):
        record.name = "app.requests"
        record.event = "request.completed"
        record.request_id = "123e4567-e89b-12d3-a456-426614174000"
        payload = json.loads(formatter.format(record))
        assert payload["request_id"] == record.request_id


class TestBoundaryExceptionRedaction:
    @pytest.fixture(
        params=[
            pytest.param(build_connection_error_record, id="connection"),
            pytest.param(build_http_error_record, id="http"),
        ]
    )
    def failure_record(self, request):
        return request.param()

    @pytest.fixture(
        params=[
            pytest.param(level, id=level.name)
            for level in (LogLevel.INFO, LogLevel.DEBUG)
        ]
    )
    def level(self, request):
        return request.param

    @pytest.fixture(
        params=[pytest.param(format, id=format.value) for format in LogFormat]
    )
    def capture(self, request, level):
        stream = StringIO()
        return stream, build_diagnostic_handler(
            LoggingSettings(format=request.param, level=level), stream
        )

    def test_connection_and_http_payloads_stay_out_of_diagnostics(
        self, failure_record, capture
    ):
        stream, handler = capture
        original_error = failure_record.exc_info[1]
        handler.handle(failure_record)
        rendered = stream.getvalue()
        payload = json.loads(rendered.removeprefix("event "))
        assert payload["event"] == "job.failed"
        assert len(payload["exceptions"]) == 2
        assert "secret" not in rendered
        assert "authorization" not in rendered.lower()
        assert "password" not in rendered.lower()
        assert len(rendered.splitlines()) == 1
        assert failure_record.exc_info[1] is original_error


class TestProbeHttpContract:
    caller_id = "f" * 32
    response_id = "1" * 32
    valid_bodies = (
        pytest.param((verify_http.ProbeKind.HEALTH, '{"status":"ok"}'), id="health"),
        pytest.param(
            (
                verify_http.ProbeKind.SEASONS,
                '{"currentSeason":2025,"availableSeasons":[{"startYear":2025,"endYear":2026,"label":"2025-26","salaryCapCents":null}]}',
            ),
            id="seasons",
        ),
        pytest.param(
            (
                verify_http.ProbeKind.INVALID,
                '{"error":{"code":"INVALID_REQUEST","message":"The request parameters are invalid.","details":{"season":["Invalid integer."]}}}',
            ),
            id="invalid-request",
        ),
        pytest.param(
            (verify_http.ProbeKind.MISSING, '{"detail":"Not Found"}'),
            id="native-missing-route",
        ),
        pytest.param(
            (
                verify_http.ProbeKind.UNEXPECTED,
                '{"error":{"code":"INTERNAL_ERROR","message":"The API could not complete this request."}}',
            ),
            id="unexpected-error",
        ),
    )
    invalid_bodies = (
        pytest.param(
            (verify_http.ProbeKind.HEALTH, '{"status":"degraded"}'),
            id="wrong-health-status",
        ),
        pytest.param(
            (verify_http.ProbeKind.HEALTH, '{"status":"ok","payload":"unexpected"}'),
            id="unknown-health-field",
        ),
        pytest.param(
            (
                verify_http.ProbeKind.SEASONS,
                '{"currentSeason":2025,"availableSeasons":[]}',
            ),
            id="missing-seasons",
        ),
        pytest.param(
            (
                verify_http.ProbeKind.SEASONS,
                '{"currentSeason":2024,"availableSeasons":[{"startYear":2025,"endYear":2026,"label":"2025-26","salaryCapCents":null}]}',
            ),
            id="current-season-not-listed",
        ),
        pytest.param(
            (
                verify_http.ProbeKind.INVALID,
                '{"error":{"code":"INTERNAL_ERROR","message":"wrong","details":{"season":["Invalid"]}}}',
            ),
            id="wrong-validation-code",
        ),
        pytest.param(
            (
                verify_http.ProbeKind.INVALID,
                '{"error":{"code":"INVALID_REQUEST","message":"The request parameters are invalid.","details":{"other":["Invalid"]}}}',
            ),
            id="wrong-validation-field",
        ),
        pytest.param(
            (
                verify_http.ProbeKind.INVALID,
                '{"error":{"code":"INVALID_REQUEST","message":"wrong","details":{"season":["Invalid"]}}}',
            ),
            id="changed-validation-message",
        ),
        pytest.param(
            (verify_http.ProbeKind.MISSING, '{"detail":"wrong"}'),
            id="changed-native-missing-body",
        ),
        pytest.param(
            (
                verify_http.ProbeKind.UNEXPECTED,
                '{"error":{"code":"INTERNAL_ERROR","message":"wrong"}}',
            ),
            id="changed-internal-error-message",
        ),
    )

    def build_response(self, body, response_id):
        return httpx.Response(
            200,
            json=json.loads(body),
            headers={"X-Request-ID": response_id},
            request=httpx.Request(
                "GET", "http://probe.test", headers={"X-Request-ID": self.caller_id}
            ),
        )

    @pytest.fixture(params=valid_bodies)
    def valid(self, request):
        kind, body = request.param
        return kind, self.build_response(body, self.response_id)

    @pytest.fixture(params=invalid_bodies)
    def invalid(self, request):
        kind, body = request.param
        return kind, self.build_response(body, self.response_id)

    def test_original_native_response_contracts_are_accepted(self, valid):
        kind, response = valid
        verify_http.verify_response_body(kind, response)
        assert verify_http.read_request_id(response) == self.response_id

    def test_changed_response_body_cannot_pass_acceptance(self, invalid):
        kind, response = invalid
        with pytest.raises((AssertionError, ValidationError)):
            verify_http.verify_response_body(kind, response)

    @pytest.fixture(
        params=[
            pytest.param("g" * 32, id="non-hex-id"),
            pytest.param("A" * 32, id="uppercase-id"),
            pytest.param("1" * 31, id="short-id"),
            pytest.param("f" * 32, id="forwarded-caller-id"),
        ]
    )
    def invalid_id(self, request):
        return self.build_response('{"status":"ok"}', request.param)

    def test_only_new_lowercase_hex_request_ids_are_accepted(self, invalid_id):
        with pytest.raises((AssertionError, ValidationError)):
            verify_http.read_request_id(invalid_id)


class TestProbeCapturedLogs:
    mutations = (
        pytest.param(None, id="original-capture"),
        pytest.param("error-severity", id="wrong-error-severity"),
        pytest.param("summary-severity", id="wrong-summary-severity"),
        pytest.param("startup-severity", id="wrong-ready-severity"),
        pytest.param("malformed-id", id="invalid-request-id"),
        pytest.param("orphan-error", id="uncorrelated-duplicate-error"),
    )

    @pytest.fixture(
        params=[pytest.param(mode, id=mode.value) for mode in verify_logs.ProbeMode]
    )
    def mode(self, request):
        return request.param

    @pytest.fixture(params=mutations)
    def mutation(self, request):
        return request.param

    @pytest.fixture
    def scenario(self, tmp_path, mode, mutation):
        source = Path(__file__).parent.joinpath("fixtures", "logging")
        reports = json.loads(source.joinpath("probe-results.json").read_text())
        index = 0 if mode is verify_logs.ProbeMode.INFO else 1
        report = TypeAdapter(verify_http.ProbeReport).validate_python(
            reports[index], strict=True
        )
        raw = source.joinpath(f"probe-{mode.value}.log").read_text()
        events = [
            json.loads(line.removeprefix("event "))
            for line in raw.splitlines()
            if line.startswith(("{", "event {"))
        ]
        error = next(item for item in events if item["event"] == "request.failed")
        if mutation == "error-severity":
            error["severity"] = "INFO"
        if mutation == "summary-severity":
            next(item for item in events if item["event"] == "request.finished")[
                "severity"
            ] = "ERROR"
        if mutation == "startup-severity":
            next(item for item in events if item["event"] == "service.ready")[
                "severity"
            ] = "ERROR"
        if mutation == "malformed-id":
            error["request_id"] = "g" * 32
        if mutation == "orphan-error":
            events.append({"event": "dependency.record", "severity": "ERROR"})
        tmp_path.joinpath(f"tradevalue-logging02-{mode.value}.log").write_text(
            "\n".join(json.dumps(event) for event in events) + "\n"
        )
        return LogCaptureScenario(
            mode=mode,
            report=report,
            options=verify_logs.ProbeOptions(directory=tmp_path),
        )

    def test_real_captures_pass_and_corrupted_evidence_fails(self, scenario, mutation):
        if mutation is not None:
            with pytest.raises((AssertionError, ValidationError)):
                verify_logs.verify_mode(
                    scenario.mode, scenario.report, scenario.options
                )
            return
        result = verify_logs.verify_mode(
            scenario.mode, scenario.report, scenario.options
        )
        assert result["correlated_requests"] == (
            5 if scenario.mode is verify_logs.ProbeMode.INFO else 6
        )

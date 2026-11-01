"""Command-owned unhandled diagnostics preserve cancellation and safe cleanup data."""

import json
import logging
import os
import signal
import subprocess
import sys
import textwrap

import pytest

from app.shared.cleanup import retain_cleanup_failure
from app.shared.observability.domain import LogFormat, LoggingSettings
from app.shared.observability.formatting import SafeFormatter


class TestCommandCancellation:
    script = textwrap.dedent("""
        import asyncio
        import sys
        from backend import export_openapi
        from app.shared.cleanup import retain_cleanup_failure
        from app.shared.tests.fakes import StageOutcome

        mode = sys.argv[1]
        failure = KeyboardInterrupt("primary_secret") if mode == "keyboard" else asyncio.CancelledError("primary_secret")
        if mode == "cleanup":
            retain_cleanup_failure(failure, RuntimeError("cleanup_secret"))
        if mode == "cancelled_cleanup":
            retain_cleanup_failure(failure, asyncio.CancelledError("cleanup_secret"))
            retain_cleanup_failure(failure, asyncio.CancelledError("second_secret"))
        export_openapi._schema_text = StageOutcome(result="", failure=failure)
        raise SystemExit(export_openapi.main([]))
    """)

    @pytest.fixture(
        params=[
            pytest.param("cancelled", id="task-cancellation"),
            pytest.param("keyboard", id="keyboard-interrupt"),
            pytest.param("cleanup", id="cancellation-and-cleanup-failure"),
            pytest.param("cancelled_cleanup", id="repeated-cleanup-cancellation"),
        ]
    )
    def mode(self, request):
        return request.param

    @pytest.fixture(
        params=[pytest.param("INFO", id="normal"), pytest.param("DEBUG", id="debug")]
    )
    def level(self, request):
        return request.param

    @pytest.fixture(
        params=[pytest.param(format, id=format.value) for format in LogFormat]
    )
    def format(self, request):
        return request.param

    @pytest.fixture
    def completed(self, mode, level, format):
        return subprocess.run(
            [sys.executable, "-c", self.script, mode],
            env={**os.environ, "LOG_LEVEL": level, "LOG_FORMAT": format.value},
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_cancellation_keeps_exit_behavior_and_safe_diagnostics(
        self, completed, mode, level
    ):
        assert completed.returncode == (-signal.SIGINT if mode == "keyboard" else 1)
        assert completed.stdout == ""
        assert "secret" not in completed.stderr
        assert "Traceback" not in completed.stderr
        events = [
            json.loads(line.removeprefix("event "))
            for line in completed.stderr.splitlines()
        ]
        assert len({item["invocation_id"] for item in events}) == 1
        if mode != "cleanup" and level == "INFO":
            assert [item["event"] for item in events] == ["command.started"]
            return
        assert [item["event"] for item in events] == [
            "command.started",
            "command.failed" if mode == "cleanup" else "command.cancelled",
            "command.finished",
        ]
        assert events[-1]["outcome"] == ("failed" if mode == "cleanup" else "cancelled")
        assert events[1]["severity"] == ("ERROR" if mode == "cleanup" else "DEBUG")
        if mode == "cleanup":
            assert [item["type"] for item in events[1]["exceptions"]] == [
                "CancelledError",
                "RuntimeError",
            ]


class TestMultipleCleanupFailures:
    @pytest.fixture(
        params=[pytest.param(format, id=format.value) for format in LogFormat]
    )
    def formatter(self, request):
        return SafeFormatter(settings=LoggingSettings(format=request.param))

    @pytest.fixture
    def record(self):
        primary = ValueError("primary_secret")
        retain_cleanup_failure(primary, RuntimeError("first_secret"))
        retain_cleanup_failure(primary, OSError("second_secret"))
        return logging.LogRecord(
            "app.probe",
            logging.ERROR,
            "",
            1,
            "message_secret",
            (),
            (type(primary), primary, None),
        )

    def test_extra_cleanup_is_explicitly_truncated(self, formatter, record):
        rendered = formatter.format(record)
        payload = json.loads(rendered.removeprefix("event "))
        assert [item["type"] for item in payload["exceptions"]] == [
            "ValueError",
            "RuntimeError",
        ]
        assert payload["exceptions_truncated"] is True
        assert "secret" not in rendered

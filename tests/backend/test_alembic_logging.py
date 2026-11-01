"""Native Alembic commands separate safe diagnostics from SQL and preserve failures."""

import json
import os
import subprocess
import sys
import textwrap

import pytest

from app.shared.observability.domain import LogFormat


@pytest.fixture(
    params=[pytest.param("INFO", id="normal"), pytest.param("DEBUG", id="debug")]
)
def level(request):
    return request.param


@pytest.fixture(params=[pytest.param(format, id=format.value) for format in LogFormat])
def format(request):
    return request.param


@pytest.fixture
def environment(level, format):
    return {
        **os.environ,
        "LOG_LEVEL": level,
        "LOG_FORMAT": format.value,
        "DATABASE_URL": "postgresql://user:password_secret@127.0.0.1:1/tradevalue_test",
        "TRADEVALUE_ENV_FILE": os.devnull,
    }


class TestAlembicCommandLogging:
    @pytest.fixture(
        params=[
            pytest.param(
                (("upgrade", "head", "--sql"), 0, "offline"), id="offline-sql"
            ),
            pytest.param(
                (("upgrade", "revision_secret", "--sql"), 255, "invalid-revision"),
                id="framework-error",
            ),
            pytest.param(
                (
                    ("--raiseerr", "upgrade", "revision_secret", "--sql"),
                    1,
                    "invalid-revision",
                ),
                id="raiseerr",
            ),
            pytest.param(
                (("upgrade", "head"), 1, "connection"), id="connection-failure"
            ),
        ]
    )
    def case(self, request):
        return request.param

    @pytest.fixture
    def completed(self, case, environment):
        arguments, _, _ = case
        return subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", *arguments],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_exit_and_sql_contract_with_safe_diagnostics(self, completed, case, level):
        _, expected, mode = case
        assert completed.returncode == expected
        assert "secret" not in completed.stdout + completed.stderr
        assert "Traceback" not in completed.stderr
        assert "FAILED:" not in completed.stdout
        events = [
            json.loads(line.removeprefix("event "))
            for line in completed.stderr.splitlines()
        ]
        assert events[0]["event"] == "command.started"
        assert events[-1]["event"] == "command.finished"
        assert events[-1]["outcome"] == ("completed" if expected == 0 else "failed")
        assert len({item["invocation_id"] for item in events}) == 1
        assert sum(item["event"] == "command.failed" for item in events) == (
            expected != 0
        )
        if mode == "offline":
            assert "CREATE TABLE players" in completed.stdout
            assert "20260910_0001" in completed.stdout
            rendered = [
                item for item in events if item["event"] == "migration.step_rendered"
            ]
            assert len(rendered) == (2 if level == "DEBUG" else 0)
            assert {item["revision"] for item in rendered} <= {
                "20260910_0001",
                "20260920_0002",
            }
        if level == "INFO":
            assert not any(item["severity"] == "DEBUG" for item in events)


class TestAlembicInvalidSettings:
    @pytest.fixture(
        params=[
            pytest.param("LOG_LEVEL", id="level"),
            pytest.param("LOG_FORMAT", id="format"),
        ]
    )
    def completed(self, request):
        environment = {
            **os.environ,
            "LOG_LEVEL": "INFO",
            "LOG_FORMAT": "json",
            "DATABASE_URL": "postgresql://user:password_secret@127.0.0.1:1/tradevalue_test",
        }
        environment[request.param] = "invalid_secret"
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "backend/alembic.ini",
                "upgrade",
                "head",
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        ), request.param

    def test_invalid_settings_fail_before_connection_without_echo(self, completed):
        process, field = completed
        assert process.returncode == 255
        assert field in process.stdout + process.stderr
        assert "secret" not in process.stdout + process.stderr
        assert "OperationalError" not in process.stdout + process.stderr
        assert "Traceback" not in process.stderr


class TestAlembicProgrammaticOwnership:
    script = textwrap.dedent("""
        import asyncio
        from io import StringIO
        import json
        import logging
        import sys
        from alembic import command
        from alembic.config import Config
        from alembic.util import CommandError
        from backend.database.migrations import services
        from app.shared.tests.fakes import StageOutcome

        kind = sys.argv[1]
        failure = asyncio.CancelledError("private_secret") if kind == "cancelled" else CommandError("private_secret") if kind == "framework" else RuntimeError("private_secret")
        services.execute_migrations = StageOutcome(result=None, failure=failure)
        output = StringIO()
        handler = logging.StreamHandler(output)
        root = logging.getLogger()
        root.addHandler(handler)
        snapshot = (tuple(root.handlers), root.level, sys.excepthook)
        observed = None
        try:
            command.upgrade(Config("backend/alembic.ini"), "head")
        except BaseException as error:
            observed = error
        assert observed is failure
        assert (tuple(root.handlers), root.level, sys.excepthook) == snapshot
        assert output.getvalue() == ""
        print(json.dumps({"identity": True, "host_preserved": True}))
    """)

    @pytest.fixture(
        params=[
            pytest.param("runtime", id="runtime-error"),
            pytest.param("framework", id="framework-error"),
            pytest.param("cancelled", id="cancellation"),
        ]
    )
    def completed(self, request, environment):
        return subprocess.run(
            [sys.executable, "-c", self.script, request.param],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_library_caller_retains_exception_and_host_ownership(self, completed):
        assert completed.returncode == 0, completed.stderr
        assert json.loads(completed.stdout) == {
            "identity": True,
            "host_preserved": True,
        }
        assert "secret" not in completed.stderr
        events = [
            json.loads(line.removeprefix("event "))
            for line in completed.stderr.splitlines()
        ]
        assert not any(item["severity"] == "ERROR" for item in events)

"""Fresh-process bootstrap ownership, host coexistence and threshold contracts."""

import json
import os
import subprocess
import sys
from textwrap import dedent

import pytest


class TestLoggingBootstrap:
    configuration_script = dedent("""
        import json
        import logging
        import os
        from contextlib import ExitStack, closing
        from io import StringIO
        from app.shared.cli import ExitCode
        from app.shared.observability.domain import read_logging_settings
        from app.shared.observability.services import configure_logging

        def main() -> int:
            with ExitStack() as resources:
                return exercise_host(resources)

        def exercise_host(resources: ExitStack) -> int:
            host_output = resources.enter_context(StringIO())
            root = logging.getLogger()
            host_handler = resources.enter_context(closing(logging.StreamHandler(host_output)))
            root.addHandler(host_handler)
            resources.callback(root.removeHandler, host_handler)
            host_logger = logging.getLogger("uvicorn.error")
            host_logger.addHandler(host_handler)
            resources.callback(host_logger.removeHandler, host_handler)
            host_logger.propagate = False
            host_snapshot = (tuple(root.handlers), root.level, tuple(host_logger.handlers), host_logger.level, host_logger.propagate)
            settings = read_logging_settings(os.environ)
            resources.enter_context(closing(configure_logging(settings)))
            first = logging.getHandlerByName("tradevalue.diagnostics")
            configure_logging(settings)
            assert first is logging.getHandlerByName("tradevalue.diagnostics")
            assert (tuple(root.handlers), root.level, tuple(host_logger.handlers), host_logger.level, host_logger.propagate) == host_snapshot
            assert len(logging.getLogger("app").handlers) == 1
            logger = logging.getLogger("app.probe")
            logger.debug("secret-debug", extra={"event": "probe.debug"})
            logger.info("secret-info", extra={"event": "probe.info"})
            logging.getLogger("sqlalchemy.engine").debug("secret SQL parameters")
            logging.getLogger("httpx").info("secret URL")
            logging.getLogger("httpx").warning("secret URL", extra={"event": "secret"})
            host_logger.warning("host preserved")
            print(json.dumps({"host": host_output.getvalue(), "count": len(logging.getLogger("app").handlers)}))
            return ExitCode.SUCCESS

        if __name__ == "__main__":
            raise SystemExit(main())
    """)
    lifespan_script = dedent("""
        import json
        import logging
        import os
        import httpx
        from contextlib import ExitStack
        from unittest.mock import patch
        import asyncio
        from sqlalchemy.orm import sessionmaker
        import app.main
        from app.database import DatabaseResources
        from app.shared.cli import ExitCode
        from app.shared.tests.resources import open_sqlite_engine
        from app.shared.observability.tests.requests import parse_probe_number

        async def request_failure(application):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application, raise_app_exceptions=False), base_url="http://probe") as client:
                response = await client.get("/numbers/value_secret", headers={"Origin": "http://localhost:5173"})
                assert response.status_code == 500
                assert response.json()["error"]["code"] == "INTERNAL_ERROR"
                assert response.headers["access-control-expose-headers"] == "X-Request-ID"
                return response.headers["x-request-id"]

        async def run_lifespans(application):
            responses = []
            async with asyncio.timeout(5):
                for _ in range(2):
                    async with application.router.lifespan_context(application):
                        app.main.logger.info("secret", extra={"event": "probe.started"})
                        app.main.logger.debug("secret", extra={"event": "probe.debug"})
                        responses.append(await request_failure(application))
            return responses

        def main() -> int:
            with ExitStack() as resources:
                return exercise_lifespans(resources)

        def exercise_lifespans(resources: ExitStack) -> int:
            calls = []
            actual_create_app = app.main.create_app
            def build_resources(settings):
                assert logging.getHandlerByName("tradevalue.diagnostics") is not None
                assert settings.database_url == "postgresql://unused.invalid/tradevalue_test_startup"
                calls.append(settings.environment.value)
                engine = resources.enter_context(open_sqlite_engine())
                return DatabaseResources(engine=engine, sessions=sessionmaker(bind=engine))
            def build_application(*args, **kwargs):
                return actual_create_app(*args, **kwargs, resource_factory=build_resources)
            with patch("app.main.create_app", build_application):
                import backend.index
            assert calls == []
            assert logging.getHandlerByName("tradevalue.diagnostics") is None
            backend.index.app.add_api_route("/numbers/{key}", parse_probe_number)
            os.environ.update({"ENV": "invalid_secret", "PROD_DATABASE_URL": "postgresql://user:secret@host:invalid/db", "LOG_LEVEL": "CRITICAL", "LOG_FORMAT": "invalid_secret"})
            before = dict(os.environ)
            responses = asyncio.run(run_lifespans(backend.index.app))
            assert dict(os.environ) == before
            print(json.dumps({"calls": calls, "handlers": len(logging.getLogger("app").handlers), "database": backend.index.app.state.database, "responses": responses}))
            return ExitCode.SUCCESS

        if __name__ == "__main__":
            raise SystemExit(main())
    """)

    @pytest.fixture(
        params=[pytest.param("INFO", id="normal"), pytest.param("DEBUG", id="debug")]
    )
    def level(self, request):
        return request.param

    @pytest.fixture(
        params=[pytest.param("json", id="json"), pytest.param("text", id="text")]
    )
    def format(self, request):
        return request.param

    @pytest.fixture
    def environment(self, level, format):
        environment = dict(os.environ)
        for key in (
            "DATABASE_URL",
            "DEV_DATABASE_URL",
            "TEST_DATABASE_URL",
            "PYTHONPATH",
        ):
            environment.pop(key, None)
        return environment | {
            "TRADEVALUE_ENV_FILE": os.devnull,
            "ENV": "prod",
            "PROD_DATABASE_URL": "postgresql://unused.invalid/tradevalue_test_startup",
            "LOG_LEVEL": level,
            "LOG_FORMAT": format,
            "CORS_ORIGINS": "http://localhost:5173",
        }

    @pytest.fixture
    def configured(self, environment):
        return subprocess.run(
            [sys.executable, "-c", self.configuration_script],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_repeated_setup_preserves_host_and_emits_one_stream(
        self, configured, level
    ):
        assert configured.returncode == 0, configured.stderr
        assert json.loads(configured.stdout) == {"host": "host preserved\n", "count": 1}
        events = [
            json.loads(line.removeprefix("event "))
            for line in configured.stderr.splitlines()
        ]
        assert [event["event"] for event in events] == (
            ["probe.debug"] if level == "DEBUG" else []
        ) + ["probe.info", "dependency.record"]
        assert all(event["environment"] == "prod" for event in events)
        assert "secret" not in configured.stderr

    @pytest.fixture
    def hosted(self, environment):
        return subprocess.run(
            [sys.executable, "-c", self.lifespan_script],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_vercel_export_and_repeated_lifespans_install_before_resources(
        self, hosted, level
    ):
        assert hosted.returncode == 0, hosted.stderr
        observed = json.loads(hosted.stdout)
        assert observed["calls"] == ["prod", "prod"]
        assert observed["handlers"] == 1
        assert observed["database"] is None
        assert len(set(observed["responses"])) == 2
        events = [
            json.loads(line.removeprefix("event "))
            for line in hosted.stderr.splitlines()
        ]
        assert [event["event"] for event in events] == (
            ["probe.started"]
            + (["probe.debug", "request.started"] if level == "DEBUG" else [])
            + ["request.failed", "request.finished"]
        ) * 2
        assert {
            event["request_id"]
            for event in events
            if event["event"] == "request.failed"
        } == set(observed["responses"])
        assert "secret" not in hosted.stderr


class TestInvalidLoggingStartup:
    script = dedent("""
        import json
        import logging
        from unittest.mock import patch
        from app.main import create_runtime_app
        from app.shared.cli import ExitCode
        from app.shared.observability.domain import LoggingSettingsError

        def main() -> int:
            with patch("app.main.get_database_settings", side_effect=AssertionError("database settings read")):
                try:
                    create_runtime_app()
                except LoggingSettingsError as error:
                    print(json.dumps({"field": error.field, "handler": logging.getHandlerByName("tradevalue.diagnostics") is not None}))
            return ExitCode.SUCCESS

        if __name__ == "__main__":
            raise SystemExit(main())
    """)

    @pytest.fixture(
        params=[
            pytest.param(("LOG_LEVEL", ""), id="empty-level"),
            pytest.param(("LOG_LEVEL", "secret"), id="unknown-level"),
            pytest.param(("LOG_FORMAT", "secret"), id="unknown-format"),
        ]
    )
    def invalid_value(self, request):
        return request.param

    @pytest.fixture
    def failed(self, invalid_value):
        environment = dict(os.environ) | {
            "TRADEVALUE_ENV_FILE": os.devnull,
            "LOG_LEVEL": "INFO",
            "LOG_FORMAT": "json",
            invalid_value[0]: invalid_value[1],
        }
        return subprocess.run(
            [sys.executable, "-c", self.script],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_invalid_logging_fails_before_database_resolution(
        self, failed, invalid_value
    ):
        assert failed.returncode == 0, failed.stderr
        assert json.loads(failed.stdout) == {
            "field": invalid_value[0],
            "handler": False,
        }
        assert failed.stderr == ""


class TestConfigurationOwnershipFailures:
    script = dedent("""
        import json
        import logging
        from contextlib import closing
        from io import StringIO
        from app.shared.cli import ExitCode
        from app.shared.observability.domain import LogLevel, LoggingSettings
        from app.shared.observability.services import configure_logging, LoggingOwnershipError, LoggingConfigurationConflictError

        def main() -> int:
            with StringIO() as foreign_output, closing(logging.StreamHandler(foreign_output)) as foreign:
                foreign.set_name("tradevalue.diagnostics")
                try:
                    configure_logging(LoggingSettings())
                except LoggingOwnershipError:
                    assert logging.getHandlerByName("tradevalue.diagnostics") is foreign
                    assert logging.getLogger("app").handlers == []
            with StringIO() as output, closing(configure_logging(LoggingSettings(), stream=output)) as first:
                try:
                    configure_logging(LoggingSettings(level=LogLevel.DEBUG))
                except LoggingConfigurationConflictError:
                    assert first is logging.getHandlerByName("tradevalue.diagnostics")
                    assert logging.getLogger("app").level == logging.INFO
                    print(json.dumps({"handlers": len(logging.getLogger("app").handlers), "level": first.level}))
            return ExitCode.SUCCESS

        if __name__ == "__main__":
            raise SystemExit(main())
    """)

    @pytest.fixture
    def completed(self):
        return subprocess.run(
            [sys.executable, "-c", self.script],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_conflicting_owners_or_settings_do_not_replace_existing_configuration(
        self, completed
    ):
        assert completed.returncode == 0, completed.stderr
        assert json.loads(completed.stdout) == {"handlers": 1, "level": 20}
        assert completed.stderr == ""

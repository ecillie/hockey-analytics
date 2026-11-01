"""Resource lifetime and import isolation at composition boundaries."""

import os
import asyncio
from pathlib import Path
import subprocess
import sys
from textwrap import dedent
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session
from app.api.repository import SqlApiRepository
from app.config import (
    AppEnvironment,
    DatabaseSettings,
    ConfigurationError,
    get_database_settings,
    get_api_settings,
    load_environment,
)
from app import database
from app.database import DatabaseResources
from app.main import create_app
from app.shared.tests.resources import (
    ResourceScenario,
    ConfigurationScenario,
    EnvironmentObservation,
    open_request_session,
    open_sqlite_engine,
    ResourceFailureScenario,
    ResourceProbe,
)
from app.shared.tests.fakes import StageOutcome


class TestApplicationResources:
    @pytest.fixture
    def scenario(self):
        with open_sqlite_engine() as engine:
            scenario = ResourceScenario(
                resources=DatabaseResources(
                    engine=engine, sessions=sessionmaker(bind=engine)
                )
            )
            event.listen(engine, "engine_disposed", scenario.record_disposal)
            try:
                yield scenario
            finally:
                event.remove(engine, "engine_disposed", scenario.record_disposal)

    @pytest.fixture
    def application(self, scenario):
        settings = DatabaseSettings(
            environment=AppEnvironment.DEV, database_url="sqlite://"
        )
        application = create_app(
            database_settings=settings, resource_factory=scenario.create_resources
        )
        return application

    def test_shutdown_disposes_owned_engine(self, application, scenario):
        assert scenario.disposed == []
        with TestClient(application):
            assert application.state.database is scenario.resources
        assert scenario.disposed == [True]
        assert application.state.database is None

    def test_failure_still_disposes_owned_engine(self, application, scenario):
        with pytest.raises(RuntimeError, match="request failed"):
            with TestClient(application):
                raise RuntimeError("request failed")
        assert scenario.disposed == [True]
        assert application.state.database is None

    @pytest.fixture
    def unconfigured_client(self):
        with TestClient(create_app()) as client:
            yield client

    def test_unconfigured_application_returns_service_unavailable(
        self, unconfigured_client
    ):
        response = unconfigured_client.get("/api/health")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"


class TestImportIsolation:
    script = dedent("""
        import os
        from unittest.mock import patch
        before = dict(os.environ)
        with patch("dotenv.main.DotEnv.dict", side_effect=AssertionError("dotenv read")), patch("sqlalchemy.create_engine", side_effect=AssertionError("engine constructed")), patch("psycopg2.connect", side_effect=AssertionError("connection opened")):
            import app.config
            import app.database
            import app.api.service
            import app.ScriptingFiles.FullDataScript.capspace
            import app.ScriptingFiles.FullDataScript.ingestion
            import backend.export_openapi
            from app.main import create_app
            assert len(create_app().openapi()["paths"]) == 18
            assert backend.export_openapi._schema_text()
        assert dict(os.environ) == before
    """)

    @pytest.fixture
    def imported(self):
        return subprocess.run(
            [sys.executable, "-c", self.script],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_imports_and_schema_generation_have_no_environment_or_database_side_effects(
        self, imported
    ):
        assert imported.returncode == 0, imported.stderr


class TestEnvironmentLoading:
    @pytest.fixture
    def environment_file(self, tmp_path, monkeypatch):
        path = tmp_path.joinpath("runtime.env")
        path.write_text(
            "ENV=dev\nDB_USER=file-user\nDB_NAME=test\nDB_HOST=${DB_USER}\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("DB_USER", "exported-user")
        return path

    @pytest.fixture
    def observed_environment(self, environment_file):
        before = dict(os.environ)
        values = load_environment(env_file=environment_file)
        return EnvironmentObservation(
            user=values["DB_USER"],
            host=values["DB_HOST"],
            preserved=dict(os.environ) == before,
        )

    def test_dotenv_loading_preserves_environment_and_export_precedence(
        self, observed_environment
    ):
        assert observed_environment.user == "exported-user"
        assert observed_environment.host == "exported-user"
        assert observed_environment.preserved is True


class TestRequestSessions:
    @pytest.fixture
    def active_session(self):
        with open_sqlite_engine() as engine:
            resources = DatabaseResources(
                engine=engine, sessions=sessionmaker(bind=engine)
            )
            with open_request_session(resources) as scenario:
                yield scenario

    def test_session_closes_and_rolls_back_after_success(self, active_session):
        session, dependency = active_session.session, active_session.dependency
        assert session.in_transaction()
        dependency.close()
        assert not session.in_transaction()

    def test_session_closes_and_rolls_back_after_failure(self, active_session):
        session, dependency = active_session.session, active_session.dependency
        with pytest.raises(RuntimeError, match="request failed"):
            dependency.throw(RuntimeError("request failed"))
        assert not session.in_transaction()


class TestStructuredConfigurationErrors:
    @pytest.fixture(
        params=[
            pytest.param(("DB_CONNECT_TIMEOUT", "invalid"), id="timeout-not-integer"),
            pytest.param(("DB_CONNECT_TIMEOUT", "0"), id="timeout-zero"),
            pytest.param(("DB_POOL_SIZE", "0"), id="empty-pool"),
            pytest.param(("DB_MAX_OVERFLOW", "-1"), id="negative-overflow"),
            pytest.param(("DB_POOL_RECYCLE_SECONDS", "0"), id="recycle-zero"),
        ]
    )
    def invalid_database_values(self, request):
        name, value = request.param
        return ConfigurationScenario(
            name=name,
            values={
                "ENV": "prod",
                "DATABASE_URL": "postgresql://fixture.invalid/test",
                name: value,
            },
        )

    def test_database_configuration_error_identifies_field(
        self, invalid_database_values
    ):
        with pytest.raises(ConfigurationError) as failure:
            get_database_settings(invalid_database_values.values)
        assert failure.value.field == invalid_database_values.name

    @pytest.fixture(
        params=[
            pytest.param((("CORS_ORIGINS", " , "),), id="empty-origins"),
            pytest.param((("CORS_ORIGIN_REGEX", "["),), id="malformed-regex"),
        ]
    )
    def invalid_http_values(self, request):
        return dict(request.param)

    def test_http_configuration_error_is_structured(self, invalid_http_values):
        with pytest.raises(ConfigurationError) as failure:
            get_api_settings(invalid_http_values)
        assert failure.value.field in invalid_http_values


class TestResourceConstructionFailure:
    @pytest.fixture
    def failing_factory(self, monkeypatch):
        with open_sqlite_engine() as engine:
            disposed = []

            def record_disposal(engine):
                disposed.append(True)

            event.listen(engine, "engine_disposed", record_disposal)
            monkeypatch.setattr(database, "create_engine", StageOutcome(result=engine))
            monkeypatch.setattr(
                database,
                "sessionmaker",
                StageOutcome(
                    result=None, failure=RuntimeError("session factory failed")
                ),
            )
            try:
                yield disposed
            finally:
                event.remove(engine, "engine_disposed", record_disposal)

    @pytest.fixture
    def settings(self):
        return DatabaseSettings(
            environment=AppEnvironment.DEV, database_url="sqlite://"
        )

    def test_partial_construction_disposes_engine(self, failing_factory, settings):
        with pytest.raises(RuntimeError, match="session factory failed"):
            database.create_database_resources(settings)
        assert failing_factory == [True]


class TestConfigurationRedaction:
    @pytest.fixture
    def invalid_url(self):
        return {
            "ENV": "prod",
            "DATABASE_URL": "postgresql://fixture:fixture-password@fixture.invalid:not-a-port/test",
        }

    def test_invalid_database_url_does_not_appear_in_error(self, invalid_url):
        with pytest.raises(ConfigurationError) as failure:
            get_database_settings(invalid_url)
        assert failure.value.field == "DATABASE_URL"
        assert "fixture-password" not in str(failure.value)

    @pytest.fixture
    def settings(self):
        return DatabaseSettings(
            environment=AppEnvironment.DEV,
            database_url="postgresql://fixture:fixture-password@fixture.invalid/test",
        )

    def test_settings_representation_omits_credentials(self, settings):
        assert "fixture-password" not in repr(settings)
        assert "database_url" not in repr(settings)


class TestRequestSessionSetupCleanup:
    @pytest.fixture(
        params=[
            pytest.param(RuntimeError, id="health-error"),
            pytest.param(asyncio.CancelledError, id="health-cancelled"),
            pytest.param(KeyboardInterrupt, id="health-interrupted"),
        ]
    )
    def primary(self, request):
        failure = request.param("health failed")
        failure.__cause__ = ValueError("original cause")
        return failure

    @pytest.fixture(
        params=[pytest.param(False, id="closed"), pytest.param(True, id="close-failed")]
    )
    def scenario(self, request, primary, monkeypatch):
        cause = primary.__cause__
        cleanup = OSError("close failed") if request.param else None
        probe = ResourceProbe(
            failures={} if cleanup is None else {"session.close": cleanup}
        )
        monkeypatch.setattr(
            SqlApiRepository,
            "check_health",
            StageOutcome(
                result=None, failure=primary, name="health", events=probe.events
            ),
        )
        monkeypatch.setattr(
            Session,
            "close",
            StageOutcome(
                result=None, failure=cleanup, name="session.close", events=probe.events
            ),
        )
        return ResourceFailureScenario(
            probe=probe,
            primary=primary,
            expected=primary,
            cause=cause,
            settings=DatabaseSettings(
                environment=AppEnvironment.DEV, database_url="sqlite://"
            ),
        )

    @pytest.fixture
    def observed(self, scenario):
        def record_disposal(engine):
            scenario.probe.events.append("dispose")

        with pytest.raises(BaseException) as raised:
            with open_sqlite_engine() as engine:
                event.listen(engine, "engine_disposed", record_disposal)
                resources = DatabaseResources(
                    engine=engine, sessions=sessionmaker(bind=engine)
                )
                with open_request_session(resources):
                    raise AssertionError("health failure entered session scope")
        return raised.value

    def test_setup_failure_closes_dependency_and_engine_without_masking_primary(
        self, scenario, observed
    ):
        assert observed is scenario.primary
        assert observed.__cause__ is scenario.cause
        assert scenario.probe.events == ["health", "session.close", "dispose"]
        if "session.close" in scenario.probe.failures:
            assert (
                observed.tradevalue_cleanup is scenario.probe.failures["session.close"]
            )

"""Resource lifetime and import isolation at composition boundaries."""

from dataclasses import dataclass, field
from collections.abc import Generator
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

from fastapi import Request
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import (
    AppEnvironment,
    DatabaseSettings,
    ConfigurationError,
    get_database_settings,
    get_api_settings,
    load_environment,
)
from app.api.routes import get_service
from app.api.repository import SqlApiRepository
from app.api.service import TradeValueService
from app import database
from app.database import DatabaseResources
from app.main import create_app


@dataclass(slots=True, kw_only=True, frozen=True)
class ResourceScenario:
    resources: DatabaseResources
    disposed: list[bool] = field(default_factory=list)

    def record_disposal(self, engine) -> None:
        self.disposed.append(True)

    def create_resources(self, settings: DatabaseSettings) -> DatabaseResources:
        return self.resources


class TestApplicationResources:
    @pytest.fixture
    def scenario(self):
        engine = create_engine("sqlite://")
        scenario = ResourceScenario(
            resources=DatabaseResources(
                engine=engine, sessions=sessionmaker(bind=engine)
            )
        )
        event.listen(engine, "engine_disposed", scenario.record_disposal)
        return scenario

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

    def test_unconfigured_application_returns_service_unavailable(self):
        with TestClient(create_app()) as client:
            response = client.get("/api/health")
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

    def test_dotenv_loading_preserves_environment_and_export_precedence(
        self, environment_file
    ):
        before = dict(os.environ)
        values = load_environment(env_file=environment_file)
        assert values["DB_USER"] == "exported-user"
        assert values["DB_HOST"] == "exported-user"
        assert dict(os.environ) == before


@dataclass(slots=True, kw_only=True, frozen=True)
class RequestSessionScenario:
    session: Session
    dependency: Generator[TradeValueService]


class TestRequestSessions:
    @pytest.fixture
    def active_session(self):
        engine = create_engine("sqlite://")
        application = create_app()
        application.state.database = DatabaseResources(
            engine=engine, sessions=sessionmaker(bind=engine)
        )
        request = Request({"type": "http", "app": application})
        dependency = get_service(request)
        service = next(dependency)
        service.check_health()
        assert isinstance(service.repository, SqlApiRepository)
        yield RequestSessionScenario(
            session=service.repository.session, dependency=dependency
        )
        dependency.close()
        engine.dispose()

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
        return name, {
            "ENV": "prod",
            "DATABASE_URL": "postgresql://fixture.invalid/test",
            name: value,
        }

    def test_database_configuration_error_identifies_field(
        self, invalid_database_values
    ):
        name, values = invalid_database_values
        with pytest.raises(ConfigurationError) as failure:
            get_database_settings(values)
        assert failure.value.field == name

    @pytest.fixture(
        params=[
            pytest.param({"CORS_ORIGINS": " , "}, id="empty-origins"),
            pytest.param({"CORS_ORIGIN_REGEX": "["}, id="malformed-regex"),
        ]
    )
    def invalid_http_values(self, request):
        return request.param

    def test_http_configuration_error_is_structured(self, invalid_http_values):
        with pytest.raises(ConfigurationError) as failure:
            get_api_settings(invalid_http_values)
        assert failure.value.field in invalid_http_values


class TestResourceConstructionFailure:
    @pytest.fixture
    def failing_factory(self, monkeypatch):
        engine = create_engine("sqlite://")
        disposed = []

        def record_disposal(engine):
            disposed.append(True)

        def provide_engine(*args, **kwargs):
            return engine

        def reject_session_factory(*args, **kwargs):
            raise RuntimeError("session factory failed")

        event.listen(engine, "engine_disposed", record_disposal)
        monkeypatch.setattr(database, "create_engine", provide_engine)
        monkeypatch.setattr(database, "sessionmaker", reject_session_factory)
        return disposed

    def test_partial_construction_disposes_engine(self, failing_factory):
        settings = DatabaseSettings(
            environment=AppEnvironment.DEV, database_url="sqlite://"
        )
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

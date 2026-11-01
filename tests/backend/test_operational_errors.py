"""Operational failures retain structured details and owned cleanup order."""

import asyncio

import pytest

from app.config import ConfigurationError, get_api_settings, get_database_settings
from app.shared.environment import resolve_database_url
from app.shared.smoke import ContainerReadinessError, SmokeResponseError
from app.shared.tests.fakes import StageOutcome
from app.shared.tests.resources import ResourceProbe
from backend.database import backfill_team_stints, container_smoke, migration_smoke


class TestOperationalEnvironment:
    cases = (
        pytest.param(({}, None), id="missing"),
        pytest.param(({"DATABASE_URL": "", "TEST_DATABASE_URL": ""}, None), id="empty"),
        pytest.param(
            ({"DATABASE_URL": "", "TEST_DATABASE_URL": "test"}, "test"),
            id="empty-primary",
        ),
        pytest.param(
            ({"DATABASE_URL": "primary", "TEST_DATABASE_URL": "test"}, "primary"),
            id="primary",
        ),
        pytest.param(({"DATABASE_URL": " "}, " "), id="preserve-whitespace"),
    )

    @pytest.fixture(params=cases)
    def configured(self, request):
        return request.param

    def test_missing_empty_and_configured_values(self, configured):
        values, expected = configured
        if expected is None:
            with pytest.raises(ConfigurationError) as raised:
                resolve_database_url(values)
            assert raised.value.field == "DATABASE_URL or TEST_DATABASE_URL"
            return
        assert resolve_database_url(values) == expected


class TestIntentionalEmptySettings:
    @pytest.fixture
    def settings(self):
        return get_database_settings(
            {
                "ENV": "dev",
                "DEV_DATABASE_URL": " ",
                "DATABASE_URL": "",
                "DB_USER": "user",
                "DB_NAME": "db",
                "DB_HOST": " ",
                "DB_PASSWORD": "",
                "DB_PORT": " ",
                "DB_POOL_SIZE": "",
            }
        )

    def test_empty_settings_keep_component_and_default_fallbacks(self, settings):
        assert settings.database_url == "postgresql://user@localhost:5432/db"
        assert settings.pool_size == 2

    @pytest.fixture
    def api_settings(self):
        return get_api_settings(
            {"CORS_ORIGINS": " https://example.test, ,", "CORS_ORIGIN_REGEX": " "}
        )

    def test_empty_optional_regex_remains_absent(self, api_settings):
        assert api_settings.cors_origins == ("https://example.test",)
        assert api_settings.cors_origin_regex is None


class TestBackfillCleanup:
    cases = (
        pytest.param((RuntimeError, ("rollback", "close")), id="operation-and-cleanup"),
        pytest.param((asyncio.CancelledError, ("rollback", "close")), id="cancelled"),
        pytest.param((KeyboardInterrupt, ("rollback", "close")), id="interrupt"),
        pytest.param((None, ("commit", "rollback", "close")), id="commit-and-cleanup"),
        pytest.param((None, ("close",)), id="close-only"),
    )

    @pytest.fixture(params=cases)
    def scenario(self, request, monkeypatch):
        error_type, stages = request.param
        cause = ValueError("source cause")
        primary = None if error_type is None else error_type("operation failed")
        if primary is not None:
            primary.__cause__ = cause
        failures = {stage: RuntimeError(f"{stage} failed") for stage in stages}
        probe = ResourceProbe(failures=failures)
        monkeypatch.setattr(backfill_team_stints, "init_db", StageOutcome(result=None))
        monkeypatch.setattr(
            backfill_team_stints, "connect_database", probe.create_resource
        )
        monkeypatch.setattr(
            backfill_team_stints,
            "apply_team_stint_backfill",
            StageOutcome(result={}, failure=primary),
        )
        expected = primary if primary is not None else failures[stages[0]]
        return probe, primary, expected, cause

    def test_primary_failure_survives_cleanup(self, scenario):
        probe, primary, expected, cause = scenario
        with pytest.raises(BaseException) as raised:
            backfill_team_stints.repair_team_stints(
                backfill_team_stints.CommandOptions(
                    apply=True, first_season=None, last_season=None
                )
            )
        assert raised.value is expected
        assert probe.events == (
            ["rollback", "close"]
            if primary is not None
            else ["commit", "rollback", "close"]
            if "commit" in probe.failures
            else ["commit", "close"]
        )
        if primary is not None:
            assert raised.value.__cause__ is cause
        secondary = len(probe.failures) - int(primary is None)
        assert len(getattr(raised.value, "__notes__", [])) == secondary


class TestReadinessCause:
    @pytest.fixture
    def unavailable(self, monkeypatch):
        failure = ConnectionResetError("reset")
        monkeypatch.setattr(
            container_smoke, "request_json", StageOutcome(result=None, failure=failure)
        )
        return failure

    def test_last_transport_failure_is_retained(self, unavailable):
        with pytest.raises(ContainerReadinessError) as raised:
            container_smoke.validate(
                "http://container.test", attempts=1, delay=0, timeout=1
            )
        assert raised.value.failure is unavailable
        assert raised.value.__cause__ is unavailable
        assert raised.value.attempts == 1

    @pytest.fixture
    def unhealthy(self, monkeypatch):
        monkeypatch.setattr(
            container_smoke,
            "request_json",
            StageOutcome(result=(503, None, "starting")),
        )

    @pytest.mark.usefixtures("unhealthy")
    def test_unhealthy_response_has_structured_details(self):
        with pytest.raises(ContainerReadinessError) as raised:
            container_smoke.validate(
                "http://container.test", attempts=1, delay=0, timeout=1
            )
        failure = raised.value.failure
        assert isinstance(failure, SmokeResponseError)
        assert (failure.path, failure.status, failure.body) == (
            "/api/health",
            503,
            "starting",
        )


class TestCallerSpecificSmokePolicy:
    @pytest.fixture(
        params=(pytest.param(2004, id="historical"), pytest.param(2026, id="current"))
    )
    def seasons(self, request):
        return {"availableSeasons": [request.param], "currentSeason": request.param}

    def test_migration_retains_minimum_current_season(self, seasons):
        assert container_smoke.is_valid_seasons_response(seasons)
        assert migration_smoke.is_valid_seasons_response(seasons) == (
            seasons["currentSeason"] >= 2005
        )

    @pytest.fixture
    def teams(self):
        return [{"id": 1}]

    def test_container_accepts_populated_teams_and_migration_requires_empty(
        self, teams
    ):
        assert container_smoke.is_valid_teams_response(teams)
        assert not migration_smoke.is_valid_teams_response(teams)

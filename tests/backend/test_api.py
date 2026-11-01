import pytest
from dataclasses import replace
from collections.abc import Generator
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.api.routes import get_service
from app.main import create_app
from app.api.tests.fakes import (
    HttpScenario,
)


class TestApiContract:
    @pytest.fixture
    def scenario(self, request, service) -> Generator[HttpScenario]:
        application = create_app()
        repository = replace(
            service.repository, health_failure=getattr(request, "param", None)
        )
        service = replace(service, repository=repository)

        def provide_service():
            return service

        application.dependency_overrides[get_service] = provide_service
        with TestClient(application, raise_server_exceptions=False) as client:
            yield HttpScenario(client=client, repository=repository)

    def test_all_documented_routes_are_exposed(self, scenario):
        paths = set(scenario.client.app.openapi()["paths"])
        assert paths == {
            "/api/health",
            "/api/seasons",
            "/api/players",
            "/api/players/compare",
            "/api/players/{player_id}",
            "/api/players/{player_id}/stats",
            "/api/players/{player_id}/seasons",
            "/api/players/{player_id}/value",
            "/api/players/{player_id}/value/history",
            "/api/players/{player_id}/contract",
            "/api/rankings/hockey-value",
            "/api/teams",
            "/api/teams/{team_id}",
            "/api/teams/{team_id}/roster",
            "/api/teams/{team_id}/contracts",
            "/api/teams/{team_id}/cap",
            "/api/search",
            "/api/overview",
        }

    def test_health_checks_database_and_returns_contract_shape(self, scenario):
        response = scenario.client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert scenario.repository.health_checks == [True]

    @pytest.mark.parametrize(
        "scenario",
        [
            pytest.param(
                OperationalError("SELECT 1", {}, Exception("database unavailable")),
                id="database-unavailable",
            )
        ],
        indirect=True,
    )
    def test_database_failure_uses_shared_503_error_envelope(self, scenario):
        response = scenario.client.get("/api/health")
        assert response.status_code == 503
        assert response.json() == {
            "error": {
                "code": "DATABASE_UNAVAILABLE",
                "message": "The data service is temporarily unavailable.",
            }
        }

    def test_response_models_emit_camel_case_contract(self, scenario):
        response = scenario.client.get("/api/players?season=2025")
        assert response.status_code == 200
        assert response.json()["data"][0]["fullName"] == "Test Skater"
        assert response.json()["data"][0]["capHitCents"] == 800000000

    def test_invalid_query_uses_shared_400_error_envelope(self, scenario):
        response = scenario.client.get("/api/players?pageSize=101")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REQUEST"
        assert "pageSize" in response.json()["error"]["details"]

    def test_comparison_rejects_duplicates(self, scenario):
        response = scenario.client.get("/api/players/compare?ids=7,7&season=2025")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_COMPARISON"

    def test_search_rejects_whitespace_only_query(self, scenario):
        response = scenario.client.get("/api/search", params={"q": "  "})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REQUEST"

    def test_cors_allows_local_frontend(self, scenario):
        response = scenario.client.options(
            "/api/players",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:5173"
        )


class TestTypedRequestFailures:
    @pytest.fixture
    def client(self, service):
        application = create_app()

        def provide_service():
            return service

        application.dependency_overrides[get_service] = provide_service
        with TestClient(application) as client:
            yield client

    @pytest.mark.parametrize(
        ("url", "code", "message", "details"),
        [
            pytest.param(
                "/api/players/compare?ids=no,7&season=2025",
                "INVALID_COMPARISON",
                "Player IDs must be integers.",
                {"ids": ["Use comma-separated integer IDs."]},
                id="noninteger-comparison",
            ),
            pytest.param(
                "/api/search?q=test&types=other",
                "INVALID_SEARCH_TYPES",
                "Search types must be player or team.",
                {"types": ["Use player, team, or both."]},
                id="unknown-search-type",
            ),
            pytest.param(
                "/api/search?q=test&types=",
                "INVALID_SEARCH_TYPES",
                "Search types must be player or team.",
                {"types": ["Use player, team, or both."]},
                id="empty-search-types",
            ),
        ],
    )
    def test_public_envelopes(self, client, url, code, message, details):
        response = client.get(url)
        assert response.status_code == 400
        assert response.json() == {
            "error": {"code": code, "message": message, "details": details}
        }

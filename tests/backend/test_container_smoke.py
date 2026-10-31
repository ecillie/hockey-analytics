"""Container readiness and deployed HTTP contract behavior using saved responses."""

import pytest

from app.shared.tests.fakes import DelayRecorder, ReadinessScenario, ScriptedRequest
from backend.database import container_smoke


class TestContainerReadiness:
    success = (
        (200, {"status": "ok"}, "ok"),
        (200, {"status": "ok"}, "ok"),
        (200, {"availableSeasons": [2025], "currentSeason": 2025}, "seasons"),
        (200, [], "teams"),
    )
    expected_urls = (
        "http://container.test/api/health",
        "http://container.test/api/health",
        "http://container.test/api/health",
        "http://container.test/api/seasons",
        "http://container.test/api/teams",
    )

    @pytest.fixture(
        params=[
            pytest.param((503, None, "starting"), id="unhealthy-startup"),
            pytest.param(
                ConnectionResetError("server restarted the connection"),
                id="connection-reset",
            ),
        ]
    )
    def readiness(self, request, monkeypatch):
        scenario = ReadinessScenario(
            request=ScriptedRequest(responses=(request.param, *self.success)),
            sleep=DelayRecorder(),
        )
        monkeypatch.setattr(container_smoke, "request_json", scenario.request)
        monkeypatch.setattr(container_smoke.time, "sleep", scenario.sleep)
        return scenario

    def test_retries_readiness_then_checks_all_routes(self, readiness):
        container_smoke.validate(
            "http://container.test/", attempts=3, delay=0.01, timeout=1
        )
        assert readiness.sleep.delays == [0.01]
        assert tuple(readiness.request.urls) == self.expected_urls

    @pytest.fixture
    def unavailable(self, monkeypatch):
        scenario = ReadinessScenario(
            request=ScriptedRequest(
                responses=((503, None, "database unavailable"),) * 2
            ),
            sleep=DelayRecorder(),
        )
        monkeypatch.setattr(container_smoke, "request_json", scenario.request)
        monkeypatch.setattr(container_smoke.time, "sleep", scenario.sleep)
        return scenario

    def test_reports_readiness_failure_without_running_other_checks(self, unavailable):
        with pytest.raises(RuntimeError, match="did not become healthy"):
            container_smoke.validate(
                "http://container.test", attempts=2, delay=0, timeout=1
            )
        assert unavailable.request.urls == ["http://container.test/api/health"] * 2

    @pytest.fixture(
        params=[
            pytest.param(
                ("/api/health", (200, {"status": "degraded"}, "degraded")),
                id="invalid-health",
            ),
            pytest.param(
                ("/api/seasons", (200, {"availableSeasons": []}, "empty")),
                id="empty-seasons",
            ),
            pytest.param(("/api/teams", (200, {}, "not a list")), id="invalid-teams"),
        ]
    )
    def invalid_contract(self, request, monkeypatch):
        path, invalid_response = request.param
        responses = tuple(
            invalid_response if check_path == path else valid
            for check_path, valid in zip(
                ("/api/health", "/api/seasons", "/api/teams"),
                self.success[1:],
                strict=True,
            )
        )
        saved_request = ScriptedRequest(responses=(self.success[0], *responses))
        monkeypatch.setattr(container_smoke, "request_json", saved_request)
        return path

    def test_rejects_invalid_deployed_contract(self, invalid_contract):
        with pytest.raises(
            RuntimeError, match=f"smoke check failed for {invalid_contract}"
        ):
            container_smoke.validate(
                "http://container.test", attempts=1, delay=0, timeout=1
            )

"""Primary database failures survive all owned cleanup attempts."""

import asyncio

import pytest

from app import database
from app.config import AppEnvironment, DatabaseSettings
from app.shared.tests.resources import ResourceFailureScenario, ResourceProbe


class TestTransactionCleanup:
    cases = (
        pytest.param((RuntimeError, ("rollback",)), id="operation-and-rollback"),
        pytest.param((RuntimeError, ("close",)), id="operation-and-close"),
        pytest.param((RuntimeError, ("rollback", "close")), id="all-failures"),
        pytest.param((asyncio.CancelledError, ("rollback", "close")), id="cancelled"),
        pytest.param((KeyboardInterrupt, ("rollback", "close")), id="interrupt"),
        pytest.param((None, ("commit", "rollback", "close")), id="commit-and-cleanup"),
        pytest.param((None, ("close",)), id="close-only"),
    )

    @pytest.fixture(params=cases)
    def scenario(self, request, monkeypatch):
        error_type, stages = request.param
        cause = ValueError("original cause")
        primary = None if error_type is None else error_type("operation failed")
        if primary is not None:
            primary.__cause__ = cause
        failures: dict[str, BaseException] = {
            stage: RuntimeError(f"{stage} failed") for stage in stages
        }
        probe = ResourceProbe(failures=failures)
        monkeypatch.setattr(database, "connect_database", probe.create_resource)
        return ResourceFailureScenario(
            probe=probe,
            primary=primary,
            expected=primary if primary is not None else failures[stages[0]],
            cause=cause,
            settings=DatabaseSettings(
                environment=AppEnvironment.DEV, database_url="sqlite://"
            ),
        )

    def test_failure_identity_cause_and_cleanup_order(self, scenario):
        with pytest.raises(BaseException) as raised:
            with database.open_database_transaction():
                if scenario.primary is not None:
                    raise scenario.primary
        assert raised.value is scenario.expected
        assert scenario.probe.events == (
            ["rollback", "close"]
            if scenario.primary is not None
            else ["commit", "rollback", "close"]
            if "commit" in scenario.probe.failures
            else ["commit", "close"]
        )
        if scenario.primary is not None:
            assert raised.value.__cause__ is scenario.cause
        secondary = set(scenario.probe.failures)
        if scenario.primary is None:
            secondary.remove("commit" if "commit" in secondary else "close")
        notes = getattr(raised.value, "__notes__", [])
        assert len(notes) == len(secondary)
        assert all(any(stage in note for note in notes) for stage in secondary)


class TestEngineCleanup:
    cases = (
        pytest.param(("construction", RuntimeError, True), id="factory-and-dispose"),
        pytest.param(
            ("construction", asyncio.CancelledError, True), id="factory-cancel"
        ),
        pytest.param(("construction", RuntimeError, False), id="factory-only"),
        pytest.param(("scope", RuntimeError, True), id="operation-and-dispose"),
        pytest.param(("scope", KeyboardInterrupt, True), id="scope-interrupt"),
        pytest.param(("scope", None, True), id="dispose-only"),
    )

    @pytest.fixture(params=cases)
    def scenario(self, request, monkeypatch):
        mode, error_type, dispose_fails = request.param
        cause = ValueError("engine cause")
        primary = None if error_type is None else error_type("primary failure")
        if primary is not None:
            primary.__cause__ = cause
        failures: dict[str, BaseException] = (
            {"dispose": RuntimeError("dispose failed")} if dispose_fails else {}
        )
        if mode == "construction":
            assert primary is not None
            failures["sessions"] = primary
        probe = ResourceProbe(failures=failures)
        monkeypatch.setattr(database, "create_engine", probe.create_resource)
        monkeypatch.setattr(database, "sessionmaker", probe.create_sessions)
        return mode, ResourceFailureScenario(
            probe=probe,
            primary=primary,
            expected=primary if primary is not None else failures["dispose"],
            cause=cause,
            settings=DatabaseSettings(
                environment=AppEnvironment.DEV, database_url="sqlite://"
            ),
        )

    def test_engine_failure_retains_identity_and_attempts_disposal(self, scenario):
        mode, resources = scenario
        with pytest.raises(BaseException) as raised:
            if mode == "construction":
                database.create_database_resources(resources.settings)
            if mode == "scope":
                with database.open_database_resources(resources.settings):
                    if resources.primary is not None:
                        raise resources.primary
        assert raised.value is resources.expected
        assert resources.probe.events == ["sessions", "dispose"]
        if resources.primary is not None:
            assert raised.value.__cause__ is resources.cause
        notes = getattr(raised.value, "__notes__", [])
        assert len(notes) == int(
            resources.primary is not None and "dispose" in resources.probe.failures
        )

"""Primary database failures survive all owned cleanup attempts."""

import asyncio
import json
import logging
from datetime import date
from itertools import product

import pytest

from app import database
from app.config import AppEnvironment, DatabaseSettings
from app.shared.tests.resources import (
    CursorFailureScenario,
    CursorProbe,
    ResourceFailureScenario,
    ResourceProbe,
)
from app.ScriptingFiles.FullDataScript import ingestion, team_stints
from app.shared.tests.fakes import StageOutcome
from app.shared.observability.tests.fakes import HostileValue
from app.shared.observability.domain import LogFormat, LoggingSettings
from app.shared.observability.formatting import SafeFormatter
from app.ScriptingFiles.FullDataScript.contracts import repository as contracts
from app.ScriptingFiles.FullDataScript.contracts import (
    active_repository as active_contracts,
)
from app.ScriptingFiles.FullDataScript.roster_status.domain import RosterStatus
from app.ScriptingFiles.FullDataScript.roster_status.repository import (
    PostgresRosterRepository,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.domain import (
    MoneyPuckSnapshot,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.repository import (
    PostgresMoneyPuckRepository,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.domain import (
    NhlStatsSnapshot,
    NhlRosterSnapshot,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.repository import (
    PostgresNhlStatsRepository,
    PostgresNhlRosterRepository,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.schedule.domain import (
    ScheduleSnapshot,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.schedule.repository import (
    PostgresScheduleRepository,
)


class TestOwnedCursorQueries:
    cases = (
        pytest.param((None, None, False), id="success"),
        pytest.param((None, None, True), id="close-only"),
        *(
            pytest.param(
                (failure_type, stage, close_fails),
                id=f"{failure_type.__name__}-{stage}-close-{close_fails}",
            )
            for failure_type, stage, close_fails in product(
                (RuntimeError, asyncio.CancelledError, KeyboardInterrupt),
                ("execute", "fetchone"),
                (False, True),
            )
        ),
    )
    queries = {
        "plan": team_stints.plan_team_stint_backfill,
        "apply": team_stints.apply_team_stint_backfill,
    }
    rows = {"plan": (4, 2), "apply": (4, 2, 2), "summary": (4, 2, 3)}
    results = {
        "plan": {"canonical_assignments": 4, "missing_assignments": 2},
        "apply": {
            "canonical_assignments": 4,
            "missing_assignments": 2,
            "inserted_assignments": 2,
        },
        "summary": {"players": 4, "contracts": 2, "contract_seasons": 3, "cached": 1},
    }

    @pytest.fixture(
        params=[pytest.param(name, id=name) for name in ("plan", "apply", "summary")]
    )
    def operation(self, request):
        return request.param

    @pytest.fixture(params=cases)
    def scenario(self, request, operation, monkeypatch):
        failure_type, stage, close_fails = request.param
        primary = None if failure_type is None else failure_type("query_secret")
        cause = ValueError("cause_secret")
        failures = {}
        if primary is not None:
            primary.__cause__ = cause
            failures[stage] = primary
        cleanup = OSError("close_secret") if close_fails else None
        if cleanup is not None:
            failures["cursor.close"] = cleanup
        events = []
        cursor = CursorProbe(row=self.rows[operation], failures=failures, events=events)
        connection = ResourceProbe(failures={}, events=events, cursor_resource=cursor)
        monkeypatch.setattr(database, "connect_database", connection.create_resource)
        return CursorFailureScenario(
            connection=connection, primary=primary, cleanup=cleanup, cause=cause
        )

    def run_query(self, operation, connection):
        if operation == "summary":
            return ingestion.load_capwages_summary()
        return self.queries[operation](connection)

    def test_cursor_ownership_preserves_primary_and_borrowed_connection(
        self, operation, scenario
    ):
        if scenario.expected_failure is None:
            assert (
                self.run_query(operation, scenario.connection)
                == self.results[operation]
            )
        if scenario.expected_failure is not None:
            with pytest.raises(BaseException) as raised:
                self.run_query(operation, scenario.connection)
            assert raised.value is scenario.expected_failure
        events = scenario.connection.events
        assert events.count("cursor.close") == 1
        assert events.count("close") == (1 if operation == "summary" else 0)
        assert events.count("commit") == (
            1 if operation == "summary" and scenario.expected_failure is None else 0
        )
        if scenario.primary is not None:
            assert scenario.primary.__cause__ is scenario.cause
            if scenario.cleanup is not None:
                assert (
                    scenario.primary.__dict__["tradevalue_cleanup"] is scenario.cleanup
                )


class TestHostileCleanupAnnotations:
    @pytest.fixture(
        params=[
            pytest.param(RuntimeError, id="ordinary-primary"),
            pytest.param(asyncio.CancelledError, id="cancelled-primary"),
            pytest.param(KeyboardInterrupt, id="interrupted-primary"),
        ]
    )
    def failure_type(self, request):
        return request.param

    @pytest.fixture(
        params=[
            pytest.param("normal", id="repr-failure"),
            pytest.param("override", id="note-override-failure"),
            pytest.param("invalid", id="invalid-native-notes"),
        ]
    )
    def annotation_mode(self, request):
        return request.param

    @pytest.fixture
    def scenario(self, failure_type, annotation_mode, monkeypatch):
        primary = failure_type("primary_secret")
        cause = ValueError("cause_secret")
        primary.__cause__ = cause
        if annotation_mode == "override":
            primary.__dict__["add_note"] = StageOutcome(
                result=None, failure=failure_type("annotation_secret")
            )
        if annotation_mode == "invalid":
            primary.__dict__["__notes__"] = 42
        probe = ResourceProbe(
            failures={
                "rollback": RuntimeError(HostileValue()),
                "close": OSError("close_secret"),
            }
        )
        monkeypatch.setattr(database, "connect_database", probe.create_resource)
        return ResourceFailureScenario(
            probe=probe,
            primary=primary,
            expected=primary,
            cause=cause,
            settings=DatabaseSettings(
                environment=AppEnvironment.DEV, database_url="sqlite://"
            ),
        )

    @pytest.fixture(
        params=[pytest.param(format, id=format.value) for format in LogFormat]
    )
    def formatter(self, request):
        return SafeFormatter(settings=LoggingSettings(format=request.param))

    @pytest.fixture
    def record(self, scenario):
        return logging.LogRecord(
            "app.probe",
            logging.ERROR,
            "",
            1,
            "message_secret",
            (),
            (type(scenario.expected), scenario.expected, None),
        )

    def test_annotation_faults_do_not_replace_primary_or_skip_later_cleanup(
        self, scenario, formatter, record
    ):
        with pytest.raises(BaseException) as raised:
            with database.open_database_transaction():
                raise scenario.expected
        assert raised.value is scenario.expected
        assert raised.value.__cause__ is scenario.cause
        assert scenario.probe.events == ["rollback", "close"]
        assert (
            raised.value.__dict__["tradevalue_cleanup"]
            is scenario.probe.failures["rollback"]
        )
        assert raised.value.__dict__["tradevalue_cleanup_failed"] is True
        assert raised.value.__dict__["tradevalue_cleanup_truncated"] is True
        rendered = formatter.format(record)
        payload = json.loads(rendered.removeprefix("event "))
        assert payload["severity"] == "ERROR"
        assert payload["exceptions_truncated"] is True
        assert "secret" not in rendered


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


class TestAdapterCursorFailures:
    operations = (
        "roster-players",
        "roster-ltir",
        "roster-statuses",
        "roster-identities",
        "moneypuck",
        "nhl-stats",
        "nhl-roster",
        "schedule",
        "contract-report",
        "contract-context",
        "active-context",
    )

    @pytest.fixture(params=[pytest.param(name, id=name) for name in operations])
    def operation(self, request):
        return request.param

    @pytest.fixture(
        params=[
            pytest.param(kind, id=kind.__name__)
            for kind in (RuntimeError, asyncio.CancelledError, KeyboardInterrupt)
        ]
    )
    def primary(self, request):
        failure = request.param("query_secret")
        failure.__cause__ = ValueError("cause_secret")
        return failure

    @pytest.fixture(
        params=[pytest.param(False, id="closed"), pytest.param(True, id="close-failed")]
    )
    def scenario(self, request, primary, monkeypatch):
        cleanup = OSError("close_secret") if request.param else None
        failures = {"execute": primary}
        if cleanup is not None:
            failures["cursor.close"] = cleanup
        events = []
        cursor = CursorProbe(row=(1,), failures=failures, events=events)
        connection = ResourceProbe(failures={}, cursor_resource=cursor, events=events)
        monkeypatch.setattr(database, "connect_database", connection.create_resource)
        return CursorFailureScenario(
            connection=connection,
            primary=primary,
            cleanup=cleanup,
            cause=primary.__cause__,
        )

    @pytest.fixture
    def observed(self, operation, scenario):
        observed = None
        roster = PostgresRosterRepository(connection=scenario.connection)
        try:
            if operation == "roster-players":
                roster.load_players()
            if operation == "roster-ltir":
                roster.load_active_ltir_player_ids(date(2026, 1, 1))
            if operation == "roster-statuses":
                roster.bulk_update_statuses({7: RosterStatus.ACTIVE})
            if operation == "roster-identities":
                roster.save_ahl_external_ids(((7, "7", "Fixture Player"),))
            if operation == "moneypuck":
                PostgresMoneyPuckRepository(
                    transaction=database.open_database_transaction
                ).persist(MoneyPuckSnapshot(rows=(), quality=()))
            if operation == "nhl-stats":
                PostgresNhlStatsRepository(
                    transaction=database.open_database_transaction
                ).persist(NhlStatsSnapshot(rows=()))
            if operation == "nhl-roster":
                PostgresNhlRosterRepository(
                    transaction=database.open_database_transaction
                ).persist(NhlRosterSnapshot(season=2025, teams=(), players=()))
            if operation == "schedule":
                PostgresScheduleRepository(
                    transaction=database.open_database_transaction
                ).persist(ScheduleSnapshot(season=2025, games=(), records_read=0))
            if operation == "contract-report":
                contracts.load_coverage_report()
            if operation == "contract-context":
                with contracts.open_contract_repository():
                    raise scenario.primary
            if operation == "active-context":
                with active_contracts.open_active_repository():
                    raise scenario.primary
        except BaseException as failure:
            observed = failure
        return observed

    def test_primary_and_connection_ownership_survive_cursor_cleanup(
        self, observed, operation, scenario
    ):
        assert observed is scenario.primary
        assert observed.__cause__ is scenario.cause
        assert scenario.connection.events.count("cursor.close") == 1
        assert scenario.connection.events.count("close") == (
            0 if operation.startswith("roster-") else 1
        )
        if scenario.cleanup is not None:
            assert observed.tradevalue_cleanup is scenario.cleanup

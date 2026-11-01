"""Command boundaries validate before resources and preserve output contracts."""

from app.shared.tests.fakes import CommandCase
import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
import pytest
from app.ScriptingFiles.FullDataScript import capspace, populate_roster_status, run_all
from app.ScriptingFiles.FullDataScript.roster_status.errors import (
    IncompleteRosterFeedError,
)
from ml.features import build_features, replacement_level
from ml.pipelines import (
    build_model_dataset,
    load_player_stats,
    load_salary_cap,
    run_pipeline,
)
from ml.training import train_skater_value
from backend import export_openapi
from backend.database import (
    backfill_team_stints,
    container_smoke,
    migration_preflight,
    migration_smoke,
    schema_snapshot,
    verify_migrations,
)
from ml.evaluation import evaluate_skater_model, gate
from app.shared.tests.fakes import (
    CommandFailure,
    FailingAction,
    RecordingAction,
    RepairConnection,
)


class TestCommandBoundaries:
    cases = (
        pytest.param(CommandCase(module=capspace, action="init_db"), id="contracts"),
        pytest.param(
            CommandCase(module=populate_roster_status, action="init_db"), id="roster"
        ),
        pytest.param(CommandCase(module=run_all, action="run_all"), id="ingestion"),
        pytest.param(
            CommandCase(module=export_openapi, action="_schema_text"), id="openapi"
        ),
        pytest.param(
            CommandCase(module=backfill_team_stints, action="init_db"), id="repair"
        ),
        pytest.param(
            CommandCase(module=container_smoke, action="validate"), id="container"
        ),
        pytest.param(
            CommandCase(module=migration_preflight, action="database_url"),
            id="preflight",
        ),
        pytest.param(
            CommandCase(module=migration_smoke, action="get_database_settings"),
            id="migration-smoke",
        ),
        pytest.param(
            CommandCase(module=schema_snapshot, action="snapshot"), id="snapshot"
        ),
        pytest.param(
            CommandCase(module=verify_migrations, action="validate"), id="history"
        ),
        pytest.param(
            CommandCase(module=run_pipeline, action="run_pipeline"), id="pipeline"
        ),
        pytest.param(
            CommandCase(module=load_player_stats, action="load_player_stats"),
            id="players",
        ),
        pytest.param(
            CommandCase(module=load_salary_cap, action="load_salary_cap"), id="caps"
        ),
        pytest.param(
            CommandCase(module=build_model_dataset, action="build_model_dataset"),
            id="dataset",
        ),
        pytest.param(
            CommandCase(module=build_features, action="build_features"), id="features"
        ),
        pytest.param(
            CommandCase(module=replacement_level, action="calculate_replacement_level"),
            id="replacement",
        ),
        pytest.param(
            CommandCase(module=train_skater_value, action="train"), id="training"
        ),
        pytest.param(
            CommandCase(module=evaluate_skater_model, action="evaluate_model"),
            id="evaluation",
        ),
        pytest.param(
            CommandCase(module=gate, action="validate_committed_model_metadata"),
            id="gate",
        ),
    )

    @pytest.fixture(params=cases)
    def command(self, request, monkeypatch) -> CommandCase:
        case = request.param
        monkeypatch.setattr(case.module, case.action, FailingAction())
        return case

    def test_help_exits_before_opening_resources(self, command, capsys):
        with pytest.raises(SystemExit) as error:
            command.module.main(["--help"])
        assert error.value.code == 0
        captured = capsys.readouterr()
        assert "usage:" in captured.out
        assert captured.err == ""

    @pytest.fixture
    def help_process(self, command):
        invocation = ["-m", command.module.__name__]
        if command.module.__name__.startswith("backend."):
            invocation = [command.module.__file__]
        return subprocess.run(
            [sys.executable, *invocation, "--help"],
            env={**os.environ, "ENV": "", "TRADEVALUE_ENV_FILE": os.devnull},
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_executable_guard_supports_help_without_configuration(self, help_process):
        assert help_process.returncode == 0, help_process.stderr
        assert "usage:" in help_process.stdout

    def test_unknown_argument_exits_before_opening_resources(self, command, capsys):
        with pytest.raises(SystemExit) as error:
            command.module.main(["--unknown-option"])
        assert error.value.code == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "unrecognized arguments" in captured.err

    def test_failure_returns_one_and_logs_once_without_stdout(
        self, command, capsys, caplog
    ):
        assert command.module.main([]) == 1
        assert capsys.readouterr().out == ""
        errors = [record for record in caplog.records if record.levelname == "ERROR"]
        assert len(errors) == 1
        assert errors[0].exc_info is not None
        assert "source unavailable" in caplog.text


class TestInvalidOptions:
    cases = (
        pytest.param(capspace, ["--workers", "0"], id="workers"),
        pytest.param(capspace, ["--batch-size", "1001"], id="batch"),
        pytest.param(
            capspace,
            ["--first-season", "2026", "--last-season", "2025"],
            id="contract-seasons",
        ),
        pytest.param(capspace, ["--apply", "--dry-run"], id="contract-modes"),
        pytest.param(
            backfill_team_stints,
            ["--first-season", "2026", "--last-season", "2025"],
            id="repair-seasons",
        ),
        pytest.param(container_smoke, ["--attempts", "0"], id="attempts"),
        pytest.param(container_smoke, ["--delay", "nan"], id="delay"),
        pytest.param(container_smoke, ["--timeout", "inf"], id="timeout"),
        pytest.param(container_smoke, ["--base-url", "file:///tmp/data"], id="url"),
        pytest.param(run_pipeline, ["--min-games", "0"], id="games"),
    )

    @pytest.fixture(
        params=tuple(pytest.param(case.values, id=case.id) for case in cases)
    )
    def invalid_command(self, request, monkeypatch):
        module, argv = request.param
        action = "init_db"
        if module is container_smoke:
            action = "validate"
        if module is run_pipeline:
            action = "run_pipeline"
        monkeypatch.setattr(module, action, FailingAction())
        return module, argv

    def test_invalid_options_are_usage_errors(self, invalid_command, capsys):
        module, argv = invalid_command
        with pytest.raises(SystemExit) as error:
            module.main(argv)
        assert error.value.code == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "error:" in captured.err
        assert "source unavailable" not in captured.err


class TestOpenApiOutput:
    @pytest.fixture
    def output(self, tmp_path) -> Path:
        return tmp_path.joinpath("outside-repo", "schema.json")

    def test_export_and_check_accept_absolute_external_output(self, output, capsys):
        assert export_openapi.main(["--output", str(output)]) == 0
        assert '"openapi"' in output.read_text()
        assert "Wrote" in capsys.readouterr().out
        assert export_openapi.main(["--output", str(output), "--check"]) == 0
        assert capsys.readouterr().out == ""

    def test_stale_schema_is_diagnostic_only(self, output, capsys, caplog):
        assert export_openapi.main(["--output", str(output), "--check"]) == 1
        assert capsys.readouterr().out == ""
        assert "stale" in caplog.text


class TestIngestionCommands:
    roster_summary = {
        "statuses_updated": 1,
        "active_count": 1,
        "minors_count": 0,
        "ltir_count": 0,
        "unknown_count": 0,
        "preserved_count": 0,
    }

    @pytest.fixture
    def events(self) -> StringIO:
        return StringIO()

    @pytest.fixture
    def runner(self, monkeypatch, events):
        monkeypatch.setattr(
            run_all,
            "run_all",
            RecordingAction(events=events, name="ingest", result={"loaded": 1}),
        )
        monkeypatch.setattr(
            run_all, "init_db", RecordingAction(events=events, name="init")
        )
        monkeypatch.setattr(
            run_all,
            "sync_roster_status",
            RecordingAction(events=events, name="roster", result=self.roster_summary),
        )
        return run_all

    @pytest.fixture
    def roster(self, monkeypatch, events):
        monkeypatch.setattr(
            populate_roster_status,
            "init_db",
            RecordingAction(events=events, name="init"),
        )
        monkeypatch.setattr(
            populate_roster_status,
            "sync_roster_status",
            RecordingAction(events=events, name="roster", result=self.roster_summary),
        )
        return populate_roster_status

    def test_runner_calls_use_case_and_emits_one_json_document(
        self, runner, events, capsys
    ):
        assert runner.main([]) == 0
        assert events.getvalue() == "ingest\ninit\nroster\n"
        assert json.loads(capsys.readouterr().out) == {"loaded": 1}

    def test_roster_emits_json(self, roster, capsys):
        assert roster.main([]) == 0
        assert json.loads(capsys.readouterr().out) == self.roster_summary

    @pytest.fixture(
        params=(
            pytest.param(
                IncompleteRosterFeedError(errors=("partial feed",)), id="incomplete"
            ),
            pytest.param(CommandFailure(source="database"), id="database"),
        )
    )
    def roster_failure(self, request, runner, roster, events, monkeypatch):
        action = RecordingAction(events=events, name="roster", failure=request.param)
        monkeypatch.setattr(runner, "sync_roster_status", action)
        monkeypatch.setattr(roster, "sync_roster_status", action)
        return request.param

    def test_roster_failures_have_stable_exits_and_no_success_output(
        self, roster_failure, runner, roster, capsys, caplog
    ):
        expected = 2 if isinstance(roster_failure, IncompleteRosterFeedError) else 1
        assert runner.main([]) == expected
        assert roster.main([]) == expected
        assert capsys.readouterr().out == ""
        assert len(caplog.records) == 2

    @pytest.fixture
    def failed_source(self, runner, monkeypatch, events):
        monkeypatch.setattr(
            runner,
            "run_all",
            RecordingAction(
                events=events, name="ingest", failure=CommandFailure(source="feed")
            ),
        )
        return runner

    def test_source_failure_stops_before_roster(self, failed_source, events, capsys):
        assert failed_source.main([]) == 1
        assert events.getvalue() == "ingest\n"
        assert capsys.readouterr().out == ""


class TestHistoricalModes:
    @pytest.fixture(
        params=(
            pytest.param([], id="default-preview"),
            pytest.param(["--dry-run"], id="explicit-preview"),
            pytest.param(["--apply"], id="apply"),
            pytest.param(["--coverage"], id="coverage"),
        )
    )
    def mode(self, request, monkeypatch):
        events = StringIO()
        monkeypatch.setattr(
            capspace, "init_db", RecordingAction(events=events, name="init")
        )
        monkeypatch.setattr(
            capspace,
            "run_historical_contracts",
            RecordingAction(events=events, name="preview", result={"preview": 1}),
        )
        monkeypatch.setattr(
            capspace,
            "track_historical_contracts",
            RecordingAction(events=events, name="apply", result={"apply": 1}),
        )
        monkeypatch.setattr(
            capspace,
            "coverage_report",
            RecordingAction(events=events, name="coverage", result={"coverage": 1}),
        )
        return request.param, events

    def test_mode_runs_one_use_case_and_prints_json(self, mode, capsys):
        argv, events = mode
        assert capspace.main(argv) == 0
        expected = "preview"
        if "--apply" in argv:
            expected = "apply"
        if "--coverage" in argv:
            expected = "coverage"
        assert events.getvalue() == f"init\n{expected}\n"
        assert json.loads(capsys.readouterr().out) == {expected: 1}


class TestRepairTransaction:
    @pytest.fixture
    def events(self, monkeypatch) -> StringIO:
        events = StringIO()
        monkeypatch.setattr(
            backfill_team_stints, "init_db", RecordingAction(events=events, name="init")
        )
        monkeypatch.setattr(
            backfill_team_stints,
            "connect_database",
            RecordingAction(
                events=events, name="connect", result=RepairConnection(events=events)
            ),
        )
        monkeypatch.setattr(
            backfill_team_stints,
            "apply_team_stint_backfill",
            RecordingAction(events=events, name="apply", result={"updated": 1}),
        )
        monkeypatch.setattr(
            backfill_team_stints,
            "plan_team_stint_backfill",
            RecordingAction(events=events, name="preview", result={"updated": 1}),
        )
        return events

    def test_default_preview_rolls_back_and_closes(self, events, capsys):
        assert backfill_team_stints.main([]) == 0
        assert events.getvalue() == "init\nconnect\npreview\nrollback\nclose\n"
        assert json.loads(capsys.readouterr().out) == {"updated": 1, "applied": False}

    def test_apply_commits_and_closes(self, events, capsys):
        assert backfill_team_stints.main(["--apply"]) == 0
        assert events.getvalue() == "init\nconnect\napply\ncommit\nclose\n"
        assert json.loads(capsys.readouterr().out) == {"updated": 1, "applied": True}

    @pytest.fixture
    def failed_repair(self, events, monkeypatch):
        monkeypatch.setattr(
            backfill_team_stints,
            "apply_team_stint_backfill",
            RecordingAction(
                events=events, name="apply", failure=CommandFailure(source="database")
            ),
        )
        return events

    def test_failed_apply_rolls_back_and_closes(self, failed_repair, capsys):
        assert backfill_team_stints.main(["--apply"]) == 1
        assert failed_repair.getvalue() == "init\nconnect\napply\nrollback\nclose\n"
        assert capsys.readouterr().out == ""


class TestReadinessFailure:
    @pytest.fixture
    def events(self, monkeypatch):
        events = StringIO()
        monkeypatch.setattr(
            container_smoke,
            "request_json",
            RecordingAction(
                events=events, name="request", result=(503, None, "starting")
            ),
        )
        monkeypatch.setattr(
            container_smoke.time, "sleep", RecordingAction(events=events, name="sleep")
        )
        return events

    def test_attempt_budget_reports_last_failure(self, events, capsys, caplog):
        assert container_smoke.main(["--attempts", "3", "--delay", "0"]) == 1
        assert events.getvalue() == "request\nsleep\nrequest\nsleep\nrequest\n"
        assert "after 3 attempts" in caplog.text
        assert "status=503 body=starting" in caplog.text
        assert capsys.readouterr().out == ""

"""Fresh-process command diagnostics preserve reports and exit contracts."""

import json
import os
import subprocess
import sys
import textwrap

import pytest

from app.shared.observability.domain import LogFormat, LogLevel
from app.shared.tests.fakes import ProcessFieldObservation, ProcessOutputObservation


class TestOpenApiLogging:
    script = textwrap.dedent("""
        import sys
        from backend import export_openapi
        from app.shared.tests.fakes import FailingAction

        def main() -> int:
            mode, output = sys.argv[1:]
            if mode == 'failure':
                export_openapi.render_schema_text = FailingAction()
            arguments = ['--output', output]
            if mode == 'stale':
                arguments.append('--check')
            return export_openapi.main(arguments)
        if __name__ == '__main__':
            raise SystemExit(main())
    """)

    @pytest.fixture(
        params=[
            pytest.param("success", id="write"),
            pytest.param("stale", id="verification-failure"),
            pytest.param("failure", id="execution-failure"),
        ]
    )
    def mode(self, request):
        return request.param

    @pytest.fixture(
        params=[pytest.param(format, id=format.value) for format in LogFormat]
    )
    def format(self, request):
        return request.param

    @pytest.fixture(
        params=[
            pytest.param(level, id=level.name)
            for level in (LogLevel.INFO, LogLevel.DEBUG)
        ]
    )
    def level(self, request):
        return request.param

    @pytest.fixture
    def output(self, tmp_path):
        return tmp_path.joinpath("path_secret", "openapi.json")

    @pytest.fixture
    def environment(self, level, format):
        return {
            **os.environ,
            "ENV": "",
            "TRADEVALUE_ENV_FILE": os.devnull,
            "LOG_LEVEL": level.name,
            "LOG_FORMAT": format.value,
        }

    @pytest.fixture
    def completed(self, mode, output, environment):
        return subprocess.run(
            [sys.executable, "-c", self.script, mode, str(output)],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_correlated_events_preserve_report_and_exit(self, completed, mode, output):
        assert completed.returncode == (0 if mode == "success" else 1)
        if mode == "success":
            assert completed.stdout == f"Wrote {output}\n"
            assert json.loads(output.read_text())["openapi"]
        if mode != "success":
            assert completed.stdout == ""
            assert not output.exists()
        events = [
            json.loads(line.removeprefix("event "))
            for line in completed.stderr.splitlines()
        ]
        assert events[0]["event"] == "command.started"
        assert events[-1]["event"] == "command.finished"
        assert events[-1]["outcome"] == ("completed" if mode == "success" else "failed")
        assert events[-1]["duration_ms"] >= 0
        assert len({item["invocation_id"] for item in events}) == 1
        assert {item["source"] for item in events} == {"openapi"}
        assert sum(item["severity"] == "ERROR" for item in events) == (
            mode != "success"
        )
        if mode == "failure":
            assert events[1]["exceptions"][0]["type"] == "CommandFailure"
        assert "source unavailable" not in completed.stderr
        assert "path_secret" not in completed.stderr


class TestInvalidCommandLogging:
    @pytest.fixture(
        params=[
            pytest.param("LOG_LEVEL", id="level"),
            pytest.param("LOG_FORMAT", id="format"),
        ]
    )
    def completed(self, request, tmp_path):
        output = tmp_path.joinpath("must-not-exist.json")
        process = subprocess.run(
            [sys.executable, "backend/export_openapi.py", "--output", str(output)],
            env={**os.environ, request.param: "invalid_secret"},
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        return ProcessOutputObservation(
            diagnostics=ProcessFieldObservation(process=process, field=request.param),
            output=output,
        )

    def test_invalid_settings_fail_before_writing_without_echo(self, completed):
        process = completed.diagnostics.process
        assert process.returncode == 2
        assert process.stdout == ""
        assert completed.diagnostics.field in process.stderr
        assert "invalid_secret" not in process.stderr
        assert "Traceback" not in process.stderr
        assert not completed.output.exists()


class TestOperationalFailureLogging:
    script = textwrap.dedent("""
        import importlib
        import sys
        from app.shared.tests.fakes import FailingAction

        def main() -> int:
            module_name, action = sys.argv[1:]
            command = importlib.import_module(module_name)
            setattr(command, action, FailingAction())
            return command.main([])
        if __name__ == '__main__':
            raise SystemExit(main())
    """)

    @pytest.fixture(
        params=[
            pytest.param(
                ("backend.database.container_smoke", "execute_command"), id="container"
            ),
            pytest.param(
                ("backend.database.schema_snapshot", "execute_command"), id="snapshot"
            ),
            pytest.param(
                ("backend.database.verify_migrations", "execute_command"), id="history"
            ),
            pytest.param(
                ("backend.database.verify_python_rules", "inspect_repository"),
                id="rules",
            ),
            pytest.param(
                ("backend.database.migration_preflight", "execute_command"),
                id="preflight",
            ),
            pytest.param(
                ("backend.database.migration_smoke", "execute_command"), id="smoke"
            ),
            pytest.param(
                ("backend.database.backfill_team_stints", "repair_team_stints"),
                id="repair",
            ),
            pytest.param(
                ("app.ScriptingFiles.FullDataScript.run_all", "run_all"), id="ingestion"
            ),
            pytest.param(
                ("app.ScriptingFiles.FullDataScript.populate_roster_status", "init_db"),
                id="roster",
            ),
            pytest.param(
                ("app.ScriptingFiles.FullDataScript.capspace", "init_db"),
                id="contracts",
            ),
            pytest.param(
                ("ml.pipelines.load_salary_cap", "load_salary_cap"), id="ml-caps"
            ),
            pytest.param(
                ("ml.pipelines.load_player_stats", "load_player_stats"), id="ml-players"
            ),
            pytest.param(
                ("ml.pipelines.build_model_dataset", "build_model_dataset"),
                id="ml-dataset",
            ),
            pytest.param(
                ("ml.pipelines.run_pipeline", "run_pipeline"), id="ml-pipeline"
            ),
            pytest.param(
                ("ml.features.build_features", "build_features"), id="ml-features"
            ),
            pytest.param(
                ("ml.features.replacement_level", "calculate_replacement_level"),
                id="ml-replacement",
            ),
            pytest.param(
                ("ml.training.train_skater_value", "train_skater_model"),
                id="ml-training",
            ),
            pytest.param(
                ("ml.evaluation.evaluate_skater_model", "evaluate_model"),
                id="ml-evaluation",
            ),
            pytest.param(
                ("ml.evaluation.gate", "validate_committed_model_metadata"),
                id="ml-gate",
            ),
        ]
    )
    def command(self, request):
        return request.param

    @pytest.fixture(
        params=[pytest.param(format, id=format.value) for format in LogFormat]
    )
    def format(self, request):
        return request.param

    @pytest.fixture(
        params=[
            pytest.param(level, id=level.name)
            for level in (LogLevel.INFO, LogLevel.DEBUG, LogLevel.CRITICAL)
        ]
    )
    def level(self, request):
        return request.param

    @pytest.fixture
    def completed(self, command, format, level):
        return subprocess.run(
            [sys.executable, "-c", self.script, *command],
            env={
                **os.environ,
                "LOG_LEVEL": level.name,
                "LOG_FORMAT": format.value,
                "ENV": "",
                "TRADEVALUE_ENV_FILE": os.devnull,
                "PYTHONWARNINGS": "ignore:Using `httpx` with `starlette.testclient` is deprecated:UserWarning",
            },
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_boundary_owns_one_safe_error_with_stable_exit(self, completed, level):
        assert completed.returncode == 1
        assert completed.stdout == ""
        assert "source unavailable" not in completed.stderr
        assert "Traceback" not in completed.stderr
        if level is LogLevel.CRITICAL:
            assert completed.stderr == ""
            return
        events = [
            json.loads(line.removeprefix("event "))
            for line in completed.stderr.splitlines()
        ]
        assert [item["event"] for item in events] == [
            "command.started",
            "command.failed",
            "command.finished",
        ]
        assert len({item["invocation_id"] for item in events}) == 1
        assert events[1]["exceptions"][0]["type"] == "CommandFailure"
        assert events[-1]["outcome"] == "failed"
        assert events[-1]["duration_ms"] >= 0

    @pytest.fixture(
        params=[
            pytest.param("LOG_LEVEL", id="invalid-level"),
            pytest.param("LOG_FORMAT", id="invalid-format"),
        ]
    )
    def invalid_completed(self, command, request):
        environment = {
            **os.environ,
            "LOG_LEVEL": "INFO",
            "LOG_FORMAT": "json",
            "ENV": "",
            "TRADEVALUE_ENV_FILE": os.devnull,
            "PYTHONWARNINGS": "ignore:Using `httpx` with `starlette.testclient` is deprecated:UserWarning",
        }
        environment[request.param] = "invalid_secret"
        process = subprocess.run(
            [sys.executable, "-c", self.script, *command],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        return ProcessFieldObservation(process=process, field=request.param)

    def test_invalid_settings_fail_before_the_work_boundary(self, invalid_completed):
        completed = invalid_completed.process
        assert completed.returncode == 2
        assert completed.stdout == ""
        assert invalid_completed.field in completed.stderr
        assert "invalid_secret" not in completed.stderr
        assert "source unavailable" not in completed.stderr
        assert "Traceback" not in completed.stderr

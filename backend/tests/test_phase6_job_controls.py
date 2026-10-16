from datetime import timedelta

from app.database_setup.run_setup import plan_setup, run_setup
from app.jobs.shared.configuration import JobConfig
from .core_source_fixtures import SourceFixtures, runner, transaction
from .execution_fixtures import NOW, config, executor
from .test_core_sources import references, accepted


def test_multiple_causes_coalesce_into_one_contract_fetch_and_are_acknowledged_once():
    fixtures = SourceFixtures()
    fixtures.events = [transaction("first"), transaction("second", kind="Contract extended")]
    worker = runner(fixtures)
    references(worker)
    assert worker.run(config("transactions")).complete
    assert len(accepted(worker, "refresh_requests")) == 2
    fixtures.calls.clear()
    report = worker.run(config("contracts"))
    assert report.complete, report.error
    assert sum("cap-space.com/person/nhl:1001" in url for url in fixtures.calls) == 1
    assert len(accepted(worker, "refresh_completions")) == 2
    assert worker.run(config("contracts", mode="refresh")).complete
    assert len(accepted(worker, "refresh_completions")) == 2


def test_failed_contract_collection_keeps_requests_pending_and_validation_has_no_ack_write():
    fixtures = SourceFixtures()
    worker = runner(fixtures)
    references(worker)
    assert worker.run(config("transactions")).complete
    fixtures.contracts[1001] = "changed schema"
    assert not worker.run(config("contracts")).complete
    assert accepted(worker, "refresh_completions") == []
    from .core_source_fixtures import contract_page
    fixtures.contracts[1001] = contract_page(1001)
    report = worker.run(config("contracts", mode="validation"))
    assert report.complete, report.error
    assert accepted(worker, "refresh_completions") == []


def test_input_freshness_requires_successful_producers_in_the_requested_scope():
    worker = executor()
    plan = plan_setup(selected=("teams_seasons","player_profiles","team_rosters"), environment="dev",
        target_environment="dev", current_season=2026, first_season=2026)
    assert run_setup(worker, plan).complete
    scope = config("team_rosters", mode="refresh", max_input_age_seconds=60)
    assert worker.run(scope).complete
    worker.now = lambda: NOW + timedelta(seconds=61)
    stale = worker.run(scope)
    assert stale.run.status == "deferred"
    from app.jobs.shared.cli import console_report
    assert console_report(stale)["reason_code"] == "STALE_INPUTS"
    assert console_report(stale)["run"]["scope"]["max_input_age_seconds"] == 60
    assert worker.run(scope.model_copy(update={"max_input_age_seconds":0})).complete


def test_dataset_setup_uses_one_range_after_all_input_producers():
    plan = plan_setup(selected=("datasets","basic_stats","moneypuck_stats"), environment="dev",
        target_environment="dev", current_season=2026, first_season=2020)
    assert plan[-1].job == "datasets"
    assert (plan[-1].first_season, plan[-1].last_season) == (2020,2026)
    assert sum(config.job == "datasets" for config in plan) == 1


def test_binding_cli_returns_configuration_error_with_sanitized_diagnostics(monkeypatch, capsys):
    from types import SimpleNamespace
    from database.pipeline import runtime
    monkeypatch.setattr(runtime,"get_database_settings",lambda:SimpleNamespace(environment=SimpleNamespace(value="prod")))
    assert runtime.main(["--environment","dev"]) == 2
    output = capsys.readouterr()
    assert "database.binding_failed" in output.err
    assert "ValueError" in output.err
    assert output.out == ""

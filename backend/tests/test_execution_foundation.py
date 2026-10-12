"""Phase 2 acceptance evidence: offline source fixtures, injected adapters, failure recovery."""
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.database_setup.run_setup import plan_setup, run_setup
from app.jobs.shared.configuration import JOBS
from app.jobs.shared.execution import JobOperation, writer_session
from app.jobs.shared.source_requests import SourceRequestError
from app.jobs.shared.upload import UploadInterrupted
from app.jobs.shared.validation import CollectionBatch
from .contract_store import ContractStore

from .execution_fixtures import (
    NOW, TEAM, SEASON, PLAYER, MEMBERSHIP, config, source, batch,
    fixture_operations, executor, latest,
)


def test_initial_dependent_load_refresh_rerun_and_correction_share_contracts():
    runner = executor()
    plan = plan_setup(selected=("team_rosters", "player_profiles", "teams_seasons"),
        environment="dev", target_environment="dev", current_season=2026, first_season=2026)
    assert [cfg.job for cfg in plan] == ["teams_seasons", "player_profiles", "team_rosters"]
    setup = run_setup(runner, plan)
    assert setup.complete
    assert latest(runner.store, "memberships", (1,)).team_id == 10
    duplicate = runner.run(config(mode="refresh"))
    assert duplicate.run.status == "no_change" and duplicate.run.counters.accepted == 2
    assert len(runner.store.rows["dev", "teams", (10,)]) == 1
    correction = batch(source("teams", {**TEAM, "name": "Corrected Team"}))
    runner.operations["teams_seasons"] = JobOperation(lambda ctx, cursor: [correction])
    refresh = runner.run(config(mode="refresh"))
    assert refresh.complete and refresh.run.status == "succeeded"
    assert len(runner.store.rows["dev", "teams", (10,)]) == 2
    assert latest(runner.store, "teams", (10,)).name == "Corrected Team"
    assert not runner.store.leased and not runner.store.locked


class InterruptingStore(ContractStore):
    interrupt = True
    uncertain = False

    @contextmanager
    def transaction(self, environment, *, conflict_scopes):
        with super().transaction(environment, conflict_scopes=conflict_scopes) as transaction:
            original = transaction.commit

            def commit():
                if transaction.batch.checkpoint is not None and transaction.batch.checkpoint.checkpoint.cursor["position"] == 2 and self.interrupt:
                    self.fail_before_commit = True
                    try:
                        return original()
                    except RuntimeError as exc:
                        raise UploadInterrupted("Injected batch interruption") from exc
                    finally:
                        self.fail_before_commit = False
                receipt = original()
                if transaction.batch.checkpoint is not None and self.uncertain:
                    self.uncertain = False
                    raise UploadInterrupted("Committed but response lost")
                return receipt

            transaction.commit = commit
            yield transaction


def test_failed_batch_resume_and_selected_rerun_preserve_other_progress():
    store = InterruptingStore()
    first = batch(source("teams", TEAM), cursor=1, final=False)
    second = batch(source("seasons", SEASON), cursor=2)
    seen = []

    def collect(ctx, cursor):
        seen.append(cursor)
        return [first, second] if cursor is None else [second]

    runner = executor(store, {"teams_seasons": JobOperation(collect), **{k: v for k, v in fixture_operations().items() if k != "teams_seasons"}})
    assert runner.run(config("player_profiles")).complete
    unrelated = dict(store.checkpoints)
    partial = runner.run(config())
    assert partial.run.status == "partial" and partial.committed_cursors == (1,)
    assert latest(store, "seasons", (2026,)) is None
    assert partial.run.counters.accepted == 1 and partial.run.counters.read == 2
    store.interrupt = False
    resumed = runner.run(config(resume=True))
    assert resumed.complete and resumed.committed_cursors == (2,) and seen == [None, 1]
    assert len(store.rows["dev", "teams", (10,)]) == 1
    assert all(store.checkpoints[key] == value for key, value in unrelated.items())


def test_unknown_commit_outcome_retries_exact_envelope_once():
    store = InterruptingStore()
    store.interrupt = False
    store.uncertain = True
    runner = executor(store)
    report = runner.run(config())
    assert report.complete and report.committed_cursors == (1,)
    assert len(store.rows["dev", "teams", (10,)]) == 1
    assert next(iter(store.checkpoints.values()))[1] == 1


@pytest.mark.parametrize("mode", ["initial", "refresh", "backfill", "validation"])
def test_invalid_batch_preserves_state_and_never_checkpoints(mode):
    runner = executor()
    assert runner.run(config()).complete
    before = latest(runner.store, "teams", (10,))
    broken = batch(source("teams", {**TEAM, "team_id": "10"}))
    runner.operations["teams_seasons"] = JobOperation(lambda ctx, cursor: [broken])
    report = runner.run(config(mode=mode))
    assert report.run.status == "failed" and report.run.counters.rejected == 1
    assert report.issues and report.committed_cursors == ()
    assert latest(runner.store, "teams", (10,)) == before
    assert len(runner.store.checkpoints) == 1


def test_unresolved_id_is_held_without_name_matching():
    def normalize(item, ctx):
        ctx.resolve("fixture", "player", "ambiguous")
        return item.payload
    runner = executor(operations={"player_profiles": JobOperation(
        lambda ctx, cursor: [batch(source("player_profiles", PLAYER))], normalize=normalize)})
    report = runner.run(config("player_profiles"))
    assert report.run.counters.unresolved == 1 and report.issues[0].code == "UNRESOLVED_IDENTITY"
    assert not runner.store.checkpoints and latest(runner.store, "player_profiles", (7,)) is None
    issue = latest(runner.store, "validation_issues", (report.issues[0].issue_id,))
    assert issue.disposition == "held"


def test_source_mapping_resolves_only_an_existing_canonical_identity():
    runner = executor()
    assert runner.run(config("player_profiles")).complete
    mapping = {"source": "fixture", "source_id": "p7", "entity_type": "player", "canonical_id": 7}
    runner.operations["source_id_mappings"] = JobOperation(lambda ctx, cursor: [batch(source("source_mappings", mapping))], ready=lambda ctx: True)
    assert runner.run(config("source_id_mappings")).complete
    resolved = []
    runner.operations["player_profiles"] = JobOperation(lambda ctx, cursor: resolved.append(ctx.resolve("fixture", "player", "p7")) or [batch()])
    assert runner.run(config("player_profiles")).complete and resolved == [7]


def test_validation_setup_uses_overlay_and_writes_nothing():
    runner = executor()
    plan = plan_setup(selected=("teams_seasons", "player_profiles", "team_rosters"), environment="dev",
        target_environment="dev", current_season=2026, first_season=2026, mode="validation")
    report = run_setup(runner, plan)
    assert report.complete and report.reports[-1].run.counters.accepted == 1
    assert not runner.store.rows and not runner.store.checkpoints and not runner.store.receipts
    assert all(not item.committed_cursors for item in report.reports)


def test_setup_holds_leases_across_jobs_and_excludes_refreshes():
    runner = executor()
    overlap = []
    base = runner.operations["player_profiles"]
    def collect(ctx, cursor):
        overlap.append(runner.run(config(mode="refresh")))
        return base.collect(ctx, cursor)
    runner.operations["player_profiles"] = JobOperation(collect)
    plan = plan_setup(selected=("teams_seasons", "player_profiles"), environment="dev",
                      target_environment="dev", current_season=2026, first_season=2026)
    assert run_setup(runner, plan).complete
    assert overlap[0].run.status == "deferred"
    assert not runner.store.leased


def test_disjoint_jobs_can_run_while_environment_leases_remain_isolated():
    runner = executor()
    with writer_session(runner.store, "dev", config().conflict_scopes):
        assert runner.run(config("player_profiles")).complete
    with runner.store.writer_lease("prod", conflict_scopes=config().conflict_scopes):
        assert runner.run(config()).complete


def test_expired_writer_session_cannot_bypass_leases():
    runner = executor()
    with writer_session(runner.store, "dev", config().conflict_scopes) as session:
        pass
    with pytest.raises(ValueError, match="session"):
        runner.run(config(), session=session)


@pytest.mark.parametrize("changes", [
    {"environment": "prod"}, {"game_types": (1,)}, {"game_types": (True,)},
    {"game_types": (2, 2)}, {"first_season": 2007}, {"last_season": 2027},
    {"job": "edge", "first_season": 2020}, {"job": "transactions", "mode": "backfill"},
    {"job": "transactions", "first_season": 2025}, {"mode": "refresh", "resume": True},
])
def test_configuration_rejects_unsupported_scopes(changes):
    with pytest.raises(ValueError):
        config(**changes)


def test_runtime_environment_checked_against_actual_executor():
    runner = executor()
    with pytest.raises(ValueError, match="environment"):
        runner.run(config(environment="prod", target_environment="prod"))
    assert not runner.store.rows


def test_backfill_current_first_edge_floor_and_transactions_exclusion():
    plan = plan_setup(selected=("teams_seasons", "edge"), environment="dev", target_environment="dev",
                      current_season=2026, first_season=2008)
    assert plan[0].first_season == 2026
    assert min(cfg.first_season for cfg in plan if cfg.job == "edge") == 2021
    historical = plan_setup(selected=("teams_seasons",), environment="dev", target_environment="dev",
                            current_season=2026, first_season=2008, last_season=2010, mode="backfill")
    assert [cfg.first_season for cfg in historical] == [2010, 2009, 2008]
    with pytest.raises(ValueError, match="backfilled"):
        plan_setup(selected=("transactions",), environment="dev", target_environment="dev", current_season=2026, mode="backfill")


@pytest.mark.parametrize("collection", [[], [CollectionBatch((), 1, None)],
    [batch(final=False)], [batch(cursor=None)], [batch(collection_complete=False)]])
def test_missing_enumeration_does_not_pass_as_empty_source(collection):
    runner = executor(operations={"teams_seasons": JobOperation(lambda ctx, cursor: collection)})
    report = runner.run(config())
    assert not report.complete
    assert not runner.store.checkpoints or report.run.status == "partial"


def test_verified_empty_population_and_terminal_states():
    runner = executor(operations={"teams_seasons": JobOperation(lambda ctx, cursor: [batch()])})
    assert runner.run(config()).run.status == "no_change"
    assert runner.run(config(enabled=False)).run.status == "disabled"
    assert runner.run(config("contracts")).run.status == "deferred"
    runner.operations["contracts"] = JobOperation(lambda ctx, cursor: [])
    assert runner.run(config("contracts")).run.status == "deferred"


def test_source_failure_stops_setup_and_preserves_committed_progress():
    runner = executor()
    def broken(ctx, cursor):
        yield batch(source("teams", TEAM), final=False)
        raise SourceRequestError("Source timeout")
    runner.operations["teams_seasons"] = JobOperation(broken)
    plan = plan_setup(selected=("teams_seasons", "player_profiles"), environment="dev", target_environment="dev", current_season=2026, first_season=2026)
    report = run_setup(runner, plan)
    assert not report.complete and len(report.reports) == 1
    assert report.reports[0].run.status == "partial"
    assert latest(runner.store, "teams", (10,)) is not None
    assert latest(runner.store, "player_profiles", (7,)) is None


def test_relationships_and_duplicate_keys_block_whole_batch():
    for records in ((source("memberships", MEMBERSHIP),), (source("teams", TEAM), source("teams", TEAM))):
        job = "team_rosters" if records[0].dataset == "memberships" else "teams_seasons"
        runner = executor(operations={job: JobOperation(lambda ctx, cursor: [batch(*records)], ready=lambda ctx: True)})
        report = runner.run(config(job))
        assert report.issues[0].code == "INVALID_BATCH"
        assert not report.complete and not runner.store.checkpoints


def test_imports_do_not_collect_schedule_or_connect_and_cli_help_is_explicit():
    root = Path(__file__).resolve().parents[2]
    modules = [f"app.jobs.{name}" for name in JOBS] + ["app.database_setup.run_setup", "app.database_setup.backfill"]
    code = '''import socket, importlib
def blocked(*args, **kwargs):
    raise AssertionError("Network during import")
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
for name in %r:
    importlib.import_module(name)
''' % modules
    result = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    for name in ("app.jobs.teams_seasons", "app.database_setup.run_setup", "app.database_setup.backfill"):
        result = subprocess.run([sys.executable, "-m", name, "--help"], cwd=root, capture_output=True, text=True, timeout=20)
        assert result.returncode == 0 and "--runtime" in result.stdout


def test_completed_resume_skips_collection_and_preserves_checkpoint():
    runner = executor()
    assert runner.run(config()).complete
    checkpoints = dict(runner.store.checkpoints)
    runner.operations["teams_seasons"] = JobOperation(lambda ctx, cursor: (_ for _ in ()).throw(AssertionError("Completed range recollected")))
    report = runner.run(config(resume=True))
    assert report.run.status == "no_change" and report.run.counters.read == 0
    assert runner.store.checkpoints == checkpoints


@pytest.mark.parametrize("mode", ["initial", "validation"])
def test_unique_source_identity_check_matches_write_and_validation_modes(mode):
    runner = executor()
    runner.operations["teams_seasons"] = JobOperation(lambda ctx, cursor: [batch(source("teams", {**TEAM, "nhl_team_id": 10}))])
    assert runner.run(config()).complete
    runner.operations["teams_seasons"] = JobOperation(lambda ctx, cursor: [batch(source("teams", {**TEAM, "team_id": 11, "nhl_team_id": 10}))])
    result = runner.run(config(mode=mode))
    assert not result.complete and "Source identity" in result.issues[0].message
    assert latest(runner.store, "teams", (11,)) is None


def test_run_counters_checkpoint_and_records_commit_atomically_before_terminal_update():
    class TerminalFailureStore(ContractStore):
        @contextmanager
        def transaction(self, environment, *, conflict_scopes):
            with super().transaction(environment, conflict_scopes=conflict_scopes) as transaction:
                original = transaction.commit
                def commit():
                    for write in transaction.batch.writes:
                        if write.dataset == "pipeline_runs" and write.decoded().status != "running":
                            raise RuntimeError("Terminal update unavailable")
                    return original()
                transaction.commit = commit
                yield transaction
    runner = executor(TerminalFailureStore())
    result = runner.run(config())
    assert not result.complete and "terminal run persistence failed" in result.error
    stored_run = latest(runner.store, "pipeline_runs", (result.run.run_id,))
    assert stored_run.status == "running" and stored_run.counters.accepted == 2
    assert latest(runner.store, "teams", (10,)) is not None
    assert next(iter(runner.store.checkpoints.values()))[0].cursor["complete"]


def test_setup_conflict_defers_before_any_selected_job_mutates_data():
    runner = executor()
    plan = plan_setup(selected=("teams_seasons", "player_profiles"), environment="dev", target_environment="dev", current_season=2026, first_season=2026)
    with runner.store.writer_lease("dev", conflict_scopes=config("player_profiles").conflict_scopes):
        result = run_setup(runner, plan)
    assert not result.complete and result.reports[0].run.status == "deferred"
    assert not runner.store.rows


def test_final_setup_gate_requires_all_declared_partitions_and_coverage_evidence():
    from app.database_setup.validate_setup import setup_partitions, validate_setup
    from app.jobs.shared.coverage import CoverageObservation
    runner = executor()
    plan = plan_setup(selected=("teams_seasons",), environment="dev", target_environment="dev", current_season=2026, first_season=2026)
    report = run_setup(runner, plan)
    partitions = setup_partitions(plan)
    assert {partition.dataset for partition in partitions} == {"teams", "seasons"}
    complete, coverage = validate_setup(report, partitions, [], current_season=2026)
    assert not complete and not coverage.complete
    evidence = [CoverageObservation(partition, 1, 1, True) for partition in partitions]
    assert validate_setup(report, partitions, evidence, current_season=2026)[0]
    with pytest.raises(ValueError, match="omitted"):
        validate_setup(report, partitions[:1], evidence[:1], current_season=2026)


def test_cli_fixture_runtime_reports_completion_and_rejects_invalid_backfills(capsys):
    from app.jobs.shared.cli import job_main, setup_main
    args = ["--environment", "dev", "--current-season", "2026", "--runtime", "tests.execution_fixtures:create_runtime"]
    assert job_main("teams_seasons", args) == 0
    assert json.loads(capsys.readouterr().out)["run"]["status"] == "succeeded"
    assert setup_main([*args, "--first-season", "2026", "--jobs", "teams_seasons", "player_profiles", "team_rosters", "--validation-only"]) == 0
    assert json.loads(capsys.readouterr().out)["complete"]
    assert job_main("contracts", args) == 1
    assert json.loads(capsys.readouterr().out)["run"]["status"] == "deferred"
    with pytest.raises(SystemExit) as error:
        job_main("transactions", [*args, "--mode", "backfill", "--validation-only"])
    assert error.value.code == 2
    with pytest.raises(SystemExit):
        setup_main([*args, "--jobs", "transactions", "--validation-only"], mode="backfill")


def test_cancellation_records_terminal_status_and_releases_writer_lease():
    def interrupted(ctx, cursor):
        raise KeyboardInterrupt()
    runner = executor(operations={"teams_seasons": JobOperation(interrupted)})
    report = runner.run(config())
    assert report.run.status == "cancelled" and not runner.store.leased
    assert latest(runner.store, "pipeline_runs", (report.run.run_id,)).status == "cancelled"
    assert not runner.store.checkpoints


def test_verified_empty_batch_does_not_report_negative_writes():
    runner = executor(operations={"teams_seasons": JobOperation(lambda ctx, cursor: [batch()])})
    report = runner.run(config())
    assert report.run.status == "no_change" and report.written == report.unchanged == 0


def test_declared_dependencies_order_jobs_even_when_catalog_is_reversed():
    from app.jobs.shared.configuration import JobSpec, ordered_jobs
    catalog = {
        "publish": JobSpec(("output",), ("normalized",)),
        "transform": JobSpec(("normalized",), ("raw",)),
        "extract": JobSpec(("raw",)),
    }
    assert ordered_jobs(catalog, catalog=catalog) == ("extract", "transform", "publish")
    # An external prerequisite is checked by readiness, not silently added to selection.
    assert ordered_jobs(("publish",), catalog=catalog) == ("publish",)
    cyclic = {"a": JobSpec(("a",), ("b",)), "b": JobSpec(("b",), ("a",))}
    with pytest.raises(ValueError, match="cycle"):
        ordered_jobs(cyclic, catalog=cyclic)


def test_historical_setup_does_not_silently_omit_selected_current_only_jobs():
    with pytest.raises(ValueError, match="historical"):
        plan_setup(selected=("teams_seasons", "transactions"), environment="dev",
                   target_environment="dev", current_season=2026, first_season=2008, last_season=2009)


@pytest.mark.parametrize("mode", ["initial", "validation"])
def test_reference_seasons_before_requested_range_are_held(mode):
    runner = executor(operations={"teams_seasons": JobOperation(lambda ctx, cursor: [batch(
        source("seasons", {"season": 2025, "end_year": 2026, "label": "2025-26"}))])})
    result = runner.run(config(mode=mode))
    assert not result.complete and "outside requested seasons" in result.issues[0].message
    assert latest(runner.store, "seasons", (2025,)) is None and not runner.store.checkpoints


def test_published_future_season_references_can_still_be_loaded():
    runner = executor(operations={"teams_seasons": JobOperation(lambda ctx, cursor: [batch(
        source("seasons", {"season": 2027, "end_year": 2028, "label": "2027-28"}))])})
    assert runner.run(config()).complete
    assert latest(runner.store, "seasons", (2027,)).end_year == 2028


def test_readiness_exceptions_record_failed_runs_without_writing_domain_data():
    def unavailable(ctx):
        raise RuntimeError("Reference audit unavailable")
    runner = executor(operations={"team_rosters": JobOperation(lambda ctx, cursor: [], ready=unavailable)})
    result = runner.run(config("team_rosters"))
    assert result.run.status == "failed" and result.error == "Reference audit unavailable"
    assert latest(runner.store, "pipeline_runs", (result.run.run_id,)).status == "failed"
    assert not runner.store.checkpoints and not runner.store.leased


def test_initial_snapshot_failure_returns_a_failed_run_report():
    class UnavailableStore(ContractStore):
        def snapshot(self, *args, **kwargs):
            raise RuntimeError("Read adapter unavailable")
    result = executor(UnavailableStore()).run(config())
    assert result.run.status == "failed" and result.error == "Read adapter unavailable"


def test_collectors_see_committed_counters_when_requesting_the_next_page():
    seen = []
    def collect(ctx, cursor):
        yield batch(source("teams", TEAM), cursor=1, final=False)
        seen.append(ctx.run.counters.model_dump())
        yield batch(source("seasons", SEASON), cursor=2)
    result = executor(operations={"teams_seasons": JobOperation(collect)}).run(config())
    assert result.complete and seen[0]["accepted"] == seen[0]["read"] == 1


def test_validation_setup_keeps_one_snapshot_despite_a_concurrent_writer():
    runner = executor()
    assert runner.run(config()).complete
    seen = []
    original = runner.operations["player_profiles"]
    runner.operations["teams_seasons"] = JobOperation(lambda ctx, cursor: [batch()])
    def collect_profile(ctx, cursor):
        runner.operations["teams_seasons"] = JobOperation(lambda ctx, cursor: [batch(source("teams", {**TEAM, "name": "Concurrent change"}))])
        assert runner.run(config()).complete  # Simulate a separate, concurrent source update.
        return original.collect(ctx, cursor)
    def collect_membership(ctx, cursor):
        seen.append(ctx.lookup("teams", (10,)).name)
        return [batch(source("memberships", MEMBERSHIP))]
    runner.operations["player_profiles"] = JobOperation(collect_profile)
    runner.operations["team_rosters"] = JobOperation(collect_membership, ready=lambda ctx: True)
    plan = plan_setup(selected=("teams_seasons", "player_profiles", "team_rosters"), environment="dev",
                      target_environment="dev", current_season=2026, first_season=2026, mode="validation")
    assert run_setup(runner, plan).complete
    assert seen == [TEAM["name"]] and latest(runner.store, "teams", (10,)).name == "Concurrent change"
    assert latest(runner.store, "memberships", (1,)) is None


def test_cursor_cycles_do_not_rewind_committed_progress():
    def collect(ctx, cursor):
        yield batch(source("teams", TEAM), cursor=1, final=False)
        yield batch(source("seasons", SEASON), cursor=2, final=False)
        yield batch(cursor=1)
    runner = executor(operations={"teams_seasons": JobOperation(collect)})
    report = runner.run(config())
    assert report.run.status == "partial" and "cursor repeated" in report.error
    assert report.committed_cursors == (1, 2)
    checkpoint = next(iter(runner.store.checkpoints.values()))[0]
    assert checkpoint.cursor == {"version": 1, "position": 2, "complete": False}


@pytest.mark.parametrize("mode", ["initial", "validation"])
def test_malformed_json_cursors_fail_the_same_way_in_write_and_validation_modes(mode):
    runner = executor(operations={"teams_seasons": JobOperation(lambda ctx, cursor: [batch(cursor={"page": float("nan")})])})
    report = runner.run(config(mode=mode))
    assert not report.complete and not runner.store.checkpoints


def test_setup_cli_retains_the_same_detailed_review_issues_as_job_reports(monkeypatch, capsys):
    from app.jobs.shared import cli
    runner = executor(operations={"teams_seasons": JobOperation(lambda ctx, cursor: [batch(source("teams", {**TEAM, "team_id": "bad"}))])})
    monkeypatch.setattr(cli, "runtime", lambda *args: runner)
    args = ["--environment", "dev", "--current-season", "2026", "--first-season", "2026", "--jobs", "teams_seasons", "--runtime", "unused:factory"]
    assert cli.setup_main(args) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["runs"][0]["issues"][0]["code"] == "INVALID_RECORD"
    assert output["runs"][0]["run"]["counters"]["rejected"] == 1


def test_shared_dependency_readers_can_run_but_dependency_writers_defer():
    runner = executor(operations={"game_schedule": JobOperation(lambda ctx, cursor: [batch()], ready=lambda ctx: True)})
    stats = config("basic_stats")
    with writer_session(runner.store, "dev", stats.write_scopes, read_scopes=stats.read_scopes):
        assert runner.run(config("game_schedule")).complete  # Shared reads of teams/seasons.
        assert runner.run(config("player_profiles")).run.status == "deferred"
        assert runner.run(stats).run.status == "deferred"  # Same exclusive output.
    assert not runner.store.read_leased and not runner.store.leased


def test_validation_setup_snapshot_failure_is_reported_without_writes():
    class UnavailableStore(ContractStore):
        def snapshot(self, *args, **kwargs):
            raise RuntimeError("Snapshot unavailable")
    runner = executor(UnavailableStore())
    report = run_setup(runner, (config(mode="validation"),))
    assert not report.complete and report.reports[0].run.status == "failed"
    assert report.reports[0].error == "Snapshot unavailable" and not runner.store.rows


def test_post_commit_read_failure_preserves_committed_counters_and_cursor_in_report():
    class TemporaryReadFailure(ContractStore):
        failed = False
        def snapshot(self, *args, **kwargs):
            if self.checkpoints and not self.failed:
                self.failed = True
                raise RuntimeError("Post-commit read failed")
            return super().snapshot(*args, **kwargs)
    runner = executor(TemporaryReadFailure())
    report = runner.run(config())
    assert report.run.status == "partial" and report.run.counters.accepted == 2
    assert report.committed_cursors == (1,) and "Post-commit" in report.error
    assert latest(runner.store, "teams", (10,)) is not None
    assert runner.run(config(resume=True)).run.status == "no_change"


def test_validation_mode_rejects_misleading_resume_requests():
    with pytest.raises(ValueError, match="Resume"):
        config(mode="validation", resume=True)


def test_setup_loads_cross_season_references_before_current_contracts():
    contract = {"contract_id": 1, "player_id": 7, "start_season": 2025, "end_season": 2026,
                "term_years": 2, "is_entry_level": False}
    mapping = {"source": "fixture", "source_id": "p7", "entity_type": "player", "canonical_id": 7}
    def references(ctx, cursor):
        year = ctx.config.first_season
        return [batch(source("teams", TEAM), source("seasons", {"season": year, "end_year": year + 1, "label": f"{year}-{year + 1}"}))]
    def contract_ready(ctx):
        return all(ctx.lookup(dataset, key) is not None for dataset, key in (
            ("player_profiles", (7,)), ("source_mappings", ("fixture", "player", "p7")),
            ("seasons", (2025,)), ("seasons", (2026,))))
    runner = executor(operations={
        "teams_seasons": JobOperation(references),
        "player_profiles": JobOperation(lambda ctx, cursor: [batch(source("player_profiles", PLAYER))]),
        "source_id_mappings": JobOperation(lambda ctx, cursor: [batch(source("source_mappings", mapping))], ready=lambda ctx: True),
        "contracts": JobOperation(lambda ctx, cursor: [batch(source("contracts", contract))], ready=contract_ready),
    })
    plan = plan_setup(selected=("contracts", "teams_seasons", "source_id_mappings", "player_profiles"),
                      environment="dev", target_environment="dev", current_season=2026, first_season=2025)
    assert run_setup(runner, plan).complete
    assert [(cfg.job, cfg.first_season) for cfg in plan[:2]] == [("teams_seasons", 2026), ("teams_seasons", 2025)]
    assert latest(runner.store, "contracts", (1,)).start_season == 2025

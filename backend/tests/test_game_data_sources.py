"""Game-data source-to-upload acceptance, corrections, scope, and recovery."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import csv
import json

import pytest

from app.database_setup.run_setup import plan_setup, run_setup
from app.jobs.game_data_operations import game_data_operations
from app.jobs.shared.cli import report_payload
from app.jobs.shared.configuration import JOBS
from app.jobs.shared.execution import ExecutionContext, JobOperation
from app.jobs.shared.run_tracking import start_run
from app.jobs.sources.edge import parse_metrics
from app.jobs.sources.feed_support import missing_player_discovery
from app.jobs.sources.moneypuck import DownloadPolicy, csv_rows, normalize_stats
from app.jobs.sources.nhl import Discovery, collect_profiles
from .execution_fixtures import NOW, config, latest
from .game_data_source_fixtures import (Fixtures, GAME, P1, P2, P3, archive, csv_body,
                                    edge_detail, event, runner, schedule_game, shot, stats)
from .test_core_sources import accepted

GAME_DATA_JOBS = tuple(game_data_operations())


def setup(executor, *, mode="initial"):
    return run_setup(executor, plan_setup(selected=GAME_DATA_JOBS, environment="dev", target_environment="dev",
        current_season=2026, first_season=2026, mode=mode))


def load_games(executor):
    report = executor.run(config("game_schedule"))
    assert report.complete, (report.error, report.issues)


def test_full_game_data_setup_and_independent_refreshes():
    executor = runner()
    result = setup(executor)
    assert result.complete, [(r.run.job, r.error, r.issues) for r in result.reports]
    assert all(accepted(executor, name) for job in GAME_DATA_JOBS for name in JOBS[job].outputs if name not in ("edge_games", "edge_events"))
    assert not any(game.game_type == 1 for game in accepted(executor, "games"))
    assert not any(game.game_id == 2026030001 for game in accepted(executor, "game_events"))
    assert latest(executor.store, "game_stats", (GAME, 10, "player", P1)).time_on_ice == 1201
    for job in GAME_DATA_JOBS:
        report = executor.run(config(job, mode="refresh", correction_lookback_days=3))
        assert report.complete, (job, report.error, report.issues)
    assert len(executor.store.rows["dev", "shots", ("moneypuck", GAME, "1")]) == 1
    edge = next(report for report in result.reports if report.run.job == "edge")
    assert {entry["dataset"] for entry in edge.source_coverage if entry["status"] == "unavailable"} == {"edge_games", "edge_events"}
    assert report_payload(edge)["source_coverage"] == edge.source_coverage


def test_validation_only_setup_uses_overlay_and_writes_nothing():
    executor = runner()
    before = deepcopy(executor.store.rows)
    result = setup(executor, mode="validation")
    assert result.complete, [(r.run.job, r.error, r.issues) for r in result.reports]
    assert executor.store.rows == before and not executor.store.checkpoints and not executor.store.receipts


@pytest.mark.parametrize("job", GAME_DATA_JOBS)
def test_missing_prerequisites_defer_without_network(job):
    fixtures = Fixtures()
    executor = runner(fixtures, seed_references=False)
    report = executor.run(config(job))
    assert report.run.status == "deferred" and not fixtures.calls


def test_schedule_deduplicates_club_games_preserves_results_and_rejects_conflicts():
    fixtures = Fixtures()
    executor = runner(fixtures)
    load_games(executor)
    assert len(accepted(executor, "games")) == 2
    def mutate(path, data):
        if "/CGY/" in path:
            data["games"][0]["homeTeam"]["score"] = 2
        return data
    fixtures.mutate = mutate
    report = executor.run(config("game_schedule", mode="refresh"))
    assert not report.complete and "Conflicting duplicate" in report.error
    assert latest(executor.store, "games", (GAME,)).home_score == 1
    assert not report.committed_cursors


@pytest.mark.parametrize("change", [
    lambda d: d.pop("games"),
    lambda d: d["games"][0].update(season=20252026),
    lambda d: d["games"][0].update(gameType="2"),
    lambda d: d["games"][0].update(gameState="BAD"),
    lambda d: d["games"][0]["homeTeam"].pop("score"),
    lambda d: d["games"][0].update(startTimeUTC="2026-10-11T18:00:00"),
])
def test_invalid_schedule_held(change):
    fixtures = Fixtures()
    executor = runner(fixtures)
    fixtures.mutate = lambda path, data: (change(data), data)[1] if "club-schedule" in path else data
    report = executor.run(config("game_schedule"))
    assert not report.complete and not report.committed_cursors and not accepted(executor, "games")


def test_game_corrections_and_configurable_lookback_skip_processed_older_games():
    fixtures = Fixtures()
    executor = runner(fixtures)
    load_games(executor)
    assert executor.run(config("game_details")).complete
    fixtures.calls.clear()
    assert executor.run(config("game_details", mode="refresh")).complete
    assert not fixtures.calls
    fixtures.play["plays"][0]["details"]["xCoord"] = 75
    report = executor.run(config("game_details", mode="refresh", correction_lookback_days=3))
    assert report.complete, report.error
    assert latest(executor.store, "game_events", ("nhl", GAME, "1")).x == 75
    assert len(executor.store.rows["dev", "game_events", ("nhl", GAME, "1")]) == 2


@pytest.mark.parametrize("change", [
    lambda f: f.box.update(id=GAME+1),
    lambda f: f.box["homeTeam"].update(score=5),
    lambda f: f.box["playerByGameStats"]["homeTeam"].pop("goalies"),
    lambda f: f.box["playerByGameStats"]["homeTeam"]["forwards"][0].update(goals=5),
    lambda f: f.play.pop("plays"),
    lambda f: f.play.update(plays=[event(), event(2)]),
    lambda f: f.play.update(plays=[event(), event(2, 20, timeInPeriod="00:10")]),
    lambda f: f.play["plays"][0].update(timeInPeriod="21:00"),
    lambda f: f.play["plays"][0]["details"].update(xCoord=101),
    lambda f: f.play["plays"][0]["details"].pop("yCoord"),
    lambda f: f.box["playerByGameStats"]["homeTeam"]["goalies"][0].update(saves=5),
])
def test_bad_game_details_never_commit(change):
    fixtures = Fixtures()
    executor = runner(fixtures)
    load_games(executor)
    change(fixtures)
    report = executor.run(config("game_details"))
    assert not report.complete and not report.committed_cursors
    assert not accepted(executor, "game_stats") and not accepted(executor, "game_events")


def test_historical_events_without_coordinates_have_explicit_limited_coverage():
    fixtures = Fixtures()
    fixtures.play["plays"][0]["details"].pop("xCoord")
    fixtures.play["plays"][0]["details"].pop("yCoord")
    executor = runner(fixtures)
    load_games(executor)
    report = executor.run(config("game_details"))
    assert report.complete
    evidence = next(row for row in report.source_coverage if row["dataset"] == "game_events")
    assert evidence["status"] == "limited" and evidence["coordinate_records"] == 0
    assert evidence["event_types"] == ["goal"]
    assert latest(executor.store, "game_events", ("nhl", GAME, "1")).x is None


def test_missing_historical_identity_retained_discovered_and_replayed():
    fixtures = Fixtures()
    missing = 8479999
    fixtures.stat_rows["skaters"][0]["playerId"] = str(missing)
    executor = runner(fixtures)
    report = executor.run(config("moneypuck_stats"))
    assert not report.complete and report.run.counters.unresolved == 2  # both game-type feeds
    assert any(issue.code == "UNRESOLVED_IDENTITY" for issue in report.issues)
    assert not report.committed_cursors and not accepted(executor, "moneypuck_skater_stats")
    cfg = config("player_profiles")
    ctx = ExecutionContext(cfg, start_run(cfg, NOW), executor.store, executor.store.snapshot("dev", accepted_before=NOW), client=executor.client)
    discovered = missing_player_discovery(ctx)
    assert discovered.player_ids == (missing,)
    discovered = replace(discovered, include_game_participation=False)
    executor.operations["player_profiles"] = JobOperation(lambda ctx, cursor: collect_profiles(ctx, cursor, discovered))
    assert executor.run(cfg).complete
    assert executor.run(config("moneypuck_stats")).complete
    assert any(row.player_id == missing for row in accepted(executor, "moneypuck_skater_stats"))


def test_moneypuck_team_total_situations_types_and_line_members_stay_distinct():
    fixtures = Fixtures()
    fixtures.stat_rows["skaters"] += [{**stats("skaters"), "team": "TOT"}, {**stats("skaters"), "situation": "5on5"}]
    executor = runner(fixtures)
    report = executor.run(config("moneypuck_stats"))
    assert report.complete, (report.error, report.issues)
    rows = accepted(executor, "moneypuck_skater_stats")
    assert len(rows) == 6
    assert {row.game_type for row in rows} == {2, 3}
    assert {row.team_scope for row in rows} == {"TEAM", "TOTAL"}
    assert {row.situation for row in rows} == {"all", "5on5"}
    assert all(row.ice_time == 1200 and row.expected_goals == 1.25 for row in rows)
    assert all(row.player_ids == (P1, P2, P3) for row in accepted(executor, "moneypuck_line_stats"))


@pytest.mark.parametrize("field,value", [("icetime", "-1"), ("I_F_xGoals", "NaN"), ("I_F_goals", "1.5"),
                                         ("onIce_xGoalsPercentage", "55"), ("I_F_points", "8"),
                                         ("team", "UNKNOWN"), ("season", "2025"), ("situation", "bad")])
def test_moneypuck_bad_measurements_totals_and_scope_fail(field, value):
    fixtures = Fixtures()
    fixtures.stat_rows["skaters"][0][field] = value
    executor = runner(fixtures)
    report = executor.run(config("moneypuck_stats"))
    assert not report.complete and not report.committed_cursors


def test_moneypuck_corrected_row_revises_same_identity():
    fixtures = Fixtures()
    executor = runner(fixtures)
    assert executor.run(config("moneypuck_stats")).complete
    fixtures.stat_rows["skaters"][0]["I_F_xGoals"] = "1.5"
    report = executor.run(config("moneypuck_stats", mode="refresh"))
    assert report.complete
    assert all(row.expected_goals == 1.5 for row in accepted(executor, "moneypuck_skater_stats"))


def test_shot_stream_scope_outcomes_coordinates_and_small_batches():
    fixtures = Fixtures()
    fixtures.shots += [shot(2, event="SHOT", goal="0"), shot(3, event="MISS", goal="0"),
                       shot(4, game_id="10001", event="GOAL"), shot(5, game_id="30001")]
    fixtures.games[2]["gameState"] = "OFF"
    executor = runner(fixtures)
    load_games(executor)
    report = executor.run(config("moneypuck_shots", max_batch_records=1))
    assert report.complete, (report.error, report.issues)
    rows = accepted(executor, "shots")
    assert len(rows) == 4 and {row.outcome for row in rows} == {"GOAL", "SAVE", "MISS"}
    assert all(row.x == 79.5 and row.coordinate_system == "moneypuck-arena-adjusted-feet" for row in rows)
    assert all(row.expected_goals == 0.12 for row in rows)
    assert len(report.committed_cursors) == 4


@pytest.mark.parametrize("change", [
    lambda f: f.shots.append(shot()),
    lambda f: f.shots[0].update(event="BLOCK"),
    lambda f: f.shots[0].update(goal="0"),
    lambda f: f.shots[0].update(xGoal="1.1"),
    lambda f: f.shots[0].update(arenaAdjustedYCord=""),
    lambda f: f.shots[0].update(season="2025"),
    lambda f: f.shots[0].update(game_id="20009"),
    lambda f: f.shots[0].update(team="CGY", game_id="30001"),
])
def test_invalid_shots_hold_without_progress(change):
    fixtures = Fixtures()
    executor = runner(fixtures)
    load_games(executor)
    change(fixtures)
    report = executor.run(config("moneypuck_shots"))
    assert not report.complete and not report.committed_cursors and not accepted(executor, "shots")


@pytest.mark.parametrize("body,archive_flag", [(b"bad", False), (b"bad", True),
    (b"a,a\n1,2\n", False), (b"a,b\n1\n", False), (b"a,b\n1,2,3\n", False)])
def test_invalid_csv_archives_and_headers(body, archive_flag):
    with pytest.raises(ValueError):
        list(csv_rows(body, ("a", "b"), archive=archive_flag)())


def test_archive_and_row_limits_are_enforced():
    body = archive(csv_body([shot(), shot(2)]))
    with pytest.raises(ValueError, match="row limit"):
        list(csv_rows(body, ("shotID",), policy=DownloadPolicy(max_rows=1), archive=True)())
    with pytest.raises(ValueError, match="bounded"):
        list(csv_rows(body, ("shotID",), policy=DownloadPolicy(max_uncompressed_bytes=1), archive=True)())
    multiple = BytesIO()
    with ZipFile(multiple, "w") as zipped:
        zipped.writestr("a.csv", b"a\n1\n")
        zipped.writestr("b.csv", b"a\n1\n")
    with pytest.raises(ValueError):
        list(csv_rows(multiple.getvalue(), ("a",), archive=True)())


def test_edge_explicit_units_breakdowns_and_dated_observations():
    executor = runner()
    assert executor.run(config("edge")).complete
    rows = accepted(executor, "edge_summaries")
    assert len(rows) == 5 and {row.entity_type for row in rows} == {"player", "team"}
    row = rows[0]
    assert row.observed_at == NOW
    assert row.metrics["skatingSpeed.speedMax.imperial"].unit == "mph"
    assert row.metrics["skatingDistance.distanceTotal.imperial"].unit == "miles"
    assert row.breakdowns["shotLocation.highDanger"]["goals"].value == 1
    executor.now = lambda: NOW + timedelta(days=1)
    executor.store.now = NOW + timedelta(days=1)
    assert executor.run(config("edge", mode="refresh")).complete
    assert len(accepted(executor, "edge_summaries")) == 10


@pytest.mark.parametrize("change", [
    lambda d: d.update(playerId=P1+9999) if "playerId" in d else d.update(teamId=99),
    lambda d: d.update(season=20252026),
    lambda d: d.update(gameType=1),
    lambda d: d.update(seasonsWithEdgeStats=[]),
    lambda d: d["skatingSpeed"]["speedMax"].update(imperial=-1),
    lambda d: d["zoneTime"].update(offensiveZonePctg=41),
    lambda d: d.clear(),
])
def test_invalid_edge_scope_metrics_and_eligibility(change):
    fixtures = Fixtures()
    fixtures.edge = lambda entity, identity, kind: (lambda d: (change(d), d)[1])(edge_detail(entity, identity, kind))
    executor = runner(fixtures)
    report = executor.run(config("edge"))
    assert not report.complete and not report.committed_cursors and not accepted(executor, "edge_summaries")


def test_required_edge_unavailable_does_not_claim_success():
    fixtures = Fixtures()
    fixtures.status["/v1/edge/team-detail/10/20262027/2"] = 404
    executor = runner(fixtures)
    report = executor.run(config("edge"))
    assert not report.complete and "404" in report.error
    assert any(entry["status"] == "unavailable" for entry in report.source_coverage)


def test_unknown_edge_measurements_retained_and_reported_without_guessing_units():
    fixtures = Fixtures()
    def response(entity, identity, kind):
        data = edge_detail(entity, identity, kind)
        data["skatingSpeed"]["mystery"] = 555
        return data
    fixtures.edge = response
    executor = runner(fixtures)
    report = executor.run(config("edge"))
    assert report.complete
    assert any("skatingSpeed.mystery" in entry.get("unknown_measurements", []) for entry in report.source_coverage)
    assert all("skatingSpeed.mystery" not in row.metrics for row in accepted(executor, "edge_summaries"))
    with pytest.raises(ValueError, match="no recognized"):
        parse_metrics({"skatingSpeed": {"mystery": 5}})


@pytest.mark.parametrize("job,path", [("game_schedule", "/v1/club-schedule-season/TOR/20262027"),
    ("game_details", f"/v1/gamecenter/{GAME}/play-by-play"),
    ("moneypuck_stats", "/moneypuck/playerData/seasonSummary/2026/regular/skaters.csv"),
    ("moneypuck_shots", "/moneypuck/downloads/shots_2026.zip"),
    ("edge", "/v1/edge/team-detail/10/20262027/2")])
def test_source_failure_preserves_accepted_data_and_checkpoint(job, path):
    fixtures = Fixtures()
    executor = runner(fixtures)
    assert setup(executor).complete
    before = {key: deepcopy(rows) for key, rows in executor.store.rows.items() if key[1] in JOBS[job].outputs}
    fixtures.status[path] = 503
    report = executor.run(config(job, mode="refresh", correction_lookback_days=3))
    assert not report.complete and "503" in report.error and not report.committed_cursors
    assert before == {key: rows for key, rows in executor.store.rows.items() if key[1] in JOBS[job].outputs}


def test_event_or_shot_removed_by_source_requires_review():
    fixtures = Fixtures()
    executor = runner(fixtures)
    assert setup(executor).complete
    fixtures.play["plays"] = []
    report = executor.run(config("game_details", mode="refresh", correction_lookback_days=3))
    assert not report.complete and "removed an accepted event" in report.error
    fixtures.shots = []
    report = executor.run(config("moneypuck_shots", mode="refresh"))
    assert not report.complete and "removed an accepted shot" in report.error
    assert accepted(executor, "game_events") and accepted(executor, "shots")


@pytest.mark.parametrize("changed", [False, True])
def test_interrupted_shot_batch_resume_is_atomic_and_rejects_changed_enumeration(monkeypatch, changed):
    from .contract_store import ContractTransaction
    fixtures = Fixtures()
    fixtures.shots = [shot(), shot(2)]
    executor = runner(fixtures)
    load_games(executor)
    original = ContractTransaction.commit
    def interrupt(transaction):
        checkpoint = transaction.batch.checkpoint
        if checkpoint is not None and checkpoint.checkpoint.job == "moneypuck_shots" and checkpoint.checkpoint.cursor["position"]["offset"] == 2:
            raise RuntimeError("Injected shot interruption")
        return original(transaction)
    monkeypatch.setattr(ContractTransaction, "commit", interrupt)
    report = executor.run(config("moneypuck_shots", max_batch_records=1))
    assert report.run.status == "partial" and len(accepted(executor, "shots")) == 1
    monkeypatch.setattr(ContractTransaction, "commit", original)
    if changed:
        fixtures.shots[1]["xGoal"] = "0.2"
    report = executor.run(config("moneypuck_shots", max_batch_records=1, resume=True))
    if changed:
        assert not report.complete and "enumeration changed" in report.error
        report = executor.run(config("moneypuck_shots", max_batch_records=1))
    assert report.complete, (report.error, report.issues)
    assert len(accepted(executor, "shots")) == 2
    assert not report.issues


def test_coverage_reports_are_persisted_on_terminal_run_even_for_empty_feeds():
    fixtures = Fixtures()
    for kind in fixtures.stat_rows:
        fixtures.stat_rows[kind] = []
    executor = runner(fixtures)
    report = executor.run(config("moneypuck_stats"))
    assert report.complete and report.source_coverage
    terminal = latest(executor.store, "pipeline_runs", (report.run.run_id,))
    assert terminal.scope["source_coverage"] == list(report.source_coverage)
    assert all(entry["enumerated_records"] == 0 and entry["expected_records"] is None for entry in report.source_coverage)


@pytest.mark.parametrize("kind", ["skaters", "goalies", "teams", "lines"])
def test_recorded_2008_moneypuck_extracts_parse_source_fields_and_units(kind):
    from app.jobs.shared.data_contracts import PlayerProfile, SeasonRecord, Team, TeamSeason
    from app.jobs.sources.feed_support import feed_record
    from app.jobs.sources.moneypuck import KINDS, line_ids
    from .game_data_source_fixtures import seed
    executor = runner(seed_references=False)
    seed(executor, "seasons", SeasonRecord(season=2008, end_year=2009, label="2008-09"))
    body = (Path(__file__).parent / f"fixtures/game_data_sources/2008_{kind}.csv").read_bytes()
    time_field = "iceTime" if kind == "teams" else "icetime"
    rows = list(csv_rows(body, ("season", "team", time_field, "situation"))())
    cfg = config("moneypuck_stats", first_season=2008, last_season=2008)
    from app.jobs.sources.moneypuck import ALIASES
    for index, raw in enumerate(rows, 1):
        team_id = index + 10
        abbreviation = ALIASES.get(raw["team"], raw["team"])
        # Multiple situations have the same team, so establish it only once.
        if any(row.abbreviation == abbreviation for row in accepted(executor, "team_seasons")):
            continue
        seed(executor, "teams", Team(team_id=team_id, nhl_team_id=team_id, name=abbreviation, abbreviation=abbreviation, active=False))
        seed(executor, "team_seasons", TeamSeason(team_id=team_id, season=2008, name=abbreviation, abbreviation=abbreviation))
    for raw in rows:
        ids = line_ids(raw) if kind == "lines" else (int(raw["playerId"]),) if kind in ("skaters", "goalies") else ()
        for identity in ids:
            if not latest(executor.store, "player_profiles", (identity,)):
                seed(executor, "player_profiles", PlayerProfile(player_id=identity, nhl_player_id=identity, first_name="Historical", last_name="Player", active=False))
    ctx = ExecutionContext(cfg, start_run(cfg, NOW), executor.store, executor.store.snapshot("dev", accepted_before=NOW))
    from app.jobs.shared.data_contracts import validate_record
    for raw in rows:
        record = feed_record(ctx, KINDS[kind], {"raw": raw, "kind": kind, "season": 2008, "game_type": 2},
                             source="moneypuck", key="fixture", raw=raw, report={})
        normalized = validate_record(KINDS[kind], normalize_stats(record, ctx))
        assert normalized.ice_time == float(raw[time_field])
        assert normalized.season == 2008


def test_optional_edge_samples_preserve_stable_ids_and_never_claim_complete_history():
    from app.jobs.game_data_operations import MetricField, SampleFeed
    from app.jobs.shared.source_requests import Response
    fixtures = Fixtures()
    metric = MetricField(("distance", "imperial"), "miles", "Audited fixture source skating distance")
    feeds = tuple(SampleFeed(dataset, "player", P1,
        "https://api-web.nhle.com/v1/edge/audited-fixture/{nhl_id}/{season}/{game_type}", ("samples",), (metric,))
        for dataset in ("edge_games", "edge_events"))
    executor = runner(fixtures, edge_sample_feeds=feeds)
    load_games(executor)
    transport = executor.client.transport
    def samples(url, **options):
        if "audited-fixture" not in url:
            return transport(url, **options)
        game_type = int(url.split("/")[-1])
        data = {"playerId": P1, "season": 20262027, "gameType": game_type,
                "samples": [{"gameId": GAME, "eventId": 123, "distance": {"imperial": 3.5}}] if game_type == 2 else []}
        return Response(200, json.dumps(data).encode())
    executor.client.transport = samples
    report = executor.run(config("edge"))
    assert report.complete, (report.error, report.issues)
    assert len(accepted(executor, "edge_games")) == len(accepted(executor, "edge_events")) == 1
    assert accepted(executor, "edge_events")[0].event_id == "123"
    assert all(entry["status"] == "limited" for entry in report.source_coverage if entry["dataset"] in ("edge_games", "edge_events"))
    executor.client.transport = lambda url, **options: Response(404, b"unavailable") if "audited-fixture" in url else transport(url, **options)
    report = executor.run(config("edge", mode="refresh"))
    assert report.complete and any(entry["status"] == "unavailable" for entry in report.source_coverage)


def test_incomplete_game_outside_lookback_is_reprocessed_even_after_team_rows_commit(monkeypatch):
    from .contract_store import ContractTransaction
    fixtures = Fixtures()
    executor = runner(fixtures)
    load_games(executor)
    original = ContractTransaction.commit
    def interrupt(transaction):
        if any(write.dataset == "game_events" for write in transaction.batch.writes):
            raise RuntimeError("Injected event interruption")
        return original(transaction)
    monkeypatch.setattr(ContractTransaction, "commit", interrupt)
    report = executor.run(config("game_details", max_batch_records=1))
    assert report.run.status == "partial" and len(accepted(executor, "game_stats")) == 6
    monkeypatch.setattr(ContractTransaction, "commit", original)
    fixtures.calls.clear()
    report = executor.run(config("game_details", mode="refresh", correction_lookback_days=0))
    assert report.complete and any("play-by-play" in call for call in fixtures.calls)
    assert len(accepted(executor, "game_events")) == 1


def test_known_redundant_moneypuck_team_columns_are_compared():
    rows = list(csv_rows(b"team,team,iceTime\nTOR,TOR,100\n", ("team", "iceTime"))())
    assert rows[0]["team"] == rows[0]["team_source_duplicate"] == "TOR"
    with pytest.raises(ValueError, match="disagree"):
        list(csv_rows(b"team,team,iceTime\nTOR,CGY,100\n", ("team", "iceTime"))())

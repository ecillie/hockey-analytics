"""Phase 3 source-to-upload tests; no network or selected database required."""
from datetime import date, timedelta
import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.database_setup.run_setup import plan_setup, run_setup
from app.jobs.core_operations import core_operations
from app.jobs.sources.contracts import parse_capspace, parse_capwages
from app.jobs.sources.nhl import Discovery, MappingCandidate, collect_profiles, normalize_stats
from app.jobs.sources.roster import RosterPolicy
from app.jobs.sources.transactions import TransactionPolicy, parse_page
from app.jobs.shared.access_contracts import make_write
from app.jobs.shared.data_contracts import Game, PlayerProfile, RosterOverride, validate_record
from app.jobs.shared.execution import JobOperation
from app.jobs.shared.source_requests import Response
from .core_source_fixtures import SourceFixtures, contract_page, page, runner, transaction
from .execution_fixtures import NOW, config, latest

CORE = tuple(core_operations())


def setup(executor, *, validation=False, selected=CORE):
    return run_setup(executor, plan_setup(selected=selected, environment="dev", target_environment="dev",
        current_season=2026, first_season=2025, mode="validation" if validation else "initial"))


def references(executor):
    result = setup(executor, selected=("teams_seasons", "player_profiles", "team_rosters", "source_id_mappings", "basic_stats"))
    assert result.complete, [(report.run.job, report.error) for report in result.reports]


def accepted(executor, dataset):
    return [history[-1].write.decoded() for (environment, name, key), history in executor.store.rows.items()
            if environment == "dev" and name == dataset]


def seed(executor, dataset, record):
    # A preaccepted manual/infrastructure prerequisite, never a source job write.
    from app.jobs.shared.access_contracts import StoredRecord
    write = make_write(dataset, record, expected_revision=None)
    executor.store.rows["dev", dataset, write.key] = [StoredRecord(write=write, revision=1, accepted_at=NOW, run_id=uuid4())]


def test_all_core_jobs_initial_setup_refresh_duplicates_and_future_contract_terms():
    executor = runner()
    result = setup(executor)
    assert result.complete, [(report.run.job, report.error, report.issues) for report in result.reports]
    assert {report.run.job for report in result.reports} == set(CORE)
    assert latest(executor.store, "player_profiles", (1003,)).active is False  # retired discovery
    assert latest(executor.store, "player_profiles", (1001,)).position == "LW"
    assert latest(executor.store, "seasons", (2027,)) is not None
    assert any(term.season == 2027 for term in accepted(executor, "contract_seasons"))
    assert len(accepted(executor, "refresh_requests")) == 1
    counts = {dataset: len(accepted(executor, dataset)) for dataset in ("contracts", "contract_seasons", "transactions", "refresh_requests", "memberships")}
    for job in CORE:
        report = executor.run(config(job, mode="refresh"))
        assert report.complete, (job, report.error, report.issues)
    assert counts == {dataset: len(accepted(executor, dataset)) for dataset in counts}
    assert len(executor.store.rows["dev", "transactions", ("usatoday", "sign-1")]) == 1
    assert latest(executor.store, "roster_state", (1001,)).status == "ACTIVE"


def test_validation_only_full_core_lifecycle_uses_overlay_and_writes_nothing():
    executor = runner()
    result = setup(executor, validation=True)
    assert result.complete, [(report.run.job, report.error, report.issues) for report in result.reports]
    assert not executor.store.rows and not executor.store.receipts and not executor.store.checkpoints


@pytest.mark.parametrize("mode", ["initial", "refresh", "backfill", "validation"])
def test_stats_grain_and_missing_values_across_execution_modes(mode):
    executor = runner()
    references(executor)
    report = executor.run(config("basic_stats", mode=mode, first_season=2025, last_season=2026))
    assert report.complete
    rows = [row for row in accepted(executor, "basic_stats") if row.player_id == 1001 and row.season == 2026]
    assert {row.team_scope for row in rows} == {"TEAM", "TOTAL"}
    assert sum(row.games_played for row in rows if row.team_scope == "TOTAL") == 10
    assert all(row.time_on_ice is None for row in rows)  # no rounded per-game TOI totals
    assert all(row.shooting_percentage == 0.1 for row in rows)


def test_stats_discovery_retains_retired_players_even_without_rosters():
    executor = runner()
    report = executor.run(config("player_profiles", first_season=2025, last_season=2025))
    assert report.complete
    assert latest(executor.store, "player_profiles", (1003,)) is not None
    assert not accepted(executor, "memberships")


def test_discover_missing_player_from_completed_game_and_explicit_dependent_ids():
    executor = runner(discovery=Discovery(player_ids=(1005,)))
    references(executor)
    game = Game(game_id=2026020001, nhl_game_id=2026020001, season=2026, game_type=2,
                home_team_id=10, away_team_id=20, start_time=NOW, status="FINAL")
    seed(executor, "games", game)
    report = executor.run(config("player_profiles", mode="refresh"))
    assert report.complete, report.error
    assert latest(executor.store, "player_profiles", (1004,)) is not None
    assert latest(executor.store, "player_profiles", (1005,)) is not None
    assert not accepted(executor, "game_stats")


@pytest.mark.parametrize("path", ["/stats/rest/en/season", "/stats/rest/en/skater/summary", "/v1/roster/TOR/current"])
def test_source_http_failure_preserves_last_valid_data_and_progress(path):
    fixtures = SourceFixtures()
    executor = runner(fixtures)
    references(executor)
    before = {key: tuple(rows) for key, rows in executor.store.rows.items() if key[1] in ("basic_stats", "memberships", "teams", "seasons")}
    fixtures.status[path] = 503
    job = "teams_seasons" if path.endswith("season") else "basic_stats" if path.endswith("summary") else "team_rosters"
    report = executor.run(config(job, mode="refresh"))
    assert report.run.status == "failed" and "503" in report.error
    assert not report.committed_cursors
    assert before == {key: tuple(rows) for key, rows in executor.store.rows.items() if key[1] in ("basic_stats", "memberships", "teams", "seasons")}


@pytest.mark.parametrize("change", [lambda data: {**data, "total": None}, lambda data: {**data, "total": data['total']+1}, lambda data: {"data": "changed", "total": 1}])
def test_incomplete_or_changed_nhl_enumeration_never_advances(change):
    fixtures = SourceFixtures()
    fixtures.mutate = lambda path, data: change(data) if path.endswith("/season") else data
    executor = runner(fixtures)
    report = executor.run(config("teams_seasons"))
    assert report.run.status == "failed" and not report.committed_cursors
    assert not accepted(executor, "teams")


def test_unknown_roster_player_held_and_reprocessed_after_profile_discovery():
    fixtures = SourceFixtures()
    executor = runner(fixtures)
    references(executor)
    old = accepted(executor, "memberships")
    fixtures.mutate = lambda path, data: {**data, "forwards": [{"id": 1006}]} if path.endswith("TOR/current") else data
    report = executor.run(config("team_rosters", mode="refresh"))
    assert report.run.status == "failed" and report.run.counters.unresolved > 0
    assert report.issues[0].code == "UNRESOLVED_IDENTITY"
    assert accepted(executor, "memberships") == old
    executor.operations["player_profiles"] = JobOperation(lambda ctx, cursor: collect_profiles(ctx, cursor, Discovery((1006,))))
    assert executor.run(config("player_profiles", mode="refresh")).complete
    assert executor.run(config("team_rosters", mode="refresh")).complete


def test_multiple_participant_signing_refresh_requests_are_atomic_and_idempotent():
    fixtures = SourceFixtures()
    fixtures.events = [transaction(player_ids=("p1", "p2"))]
    executor = runner(fixtures)
    references(executor)
    too_small = executor.run(config("transactions", max_batch_records=2))
    assert too_small.run.status == "failed" and not accepted(executor, "transactions")
    report = executor.run(config("transactions", max_batch_records=3))
    assert report.complete
    assert len(accepted(executor, "refresh_requests")) == 2
    assert {p.player_id for p in accepted(executor, "transactions")[0].participants} == {1001, 1002}
    assert executor.run(config("transactions", mode="refresh", max_batch_records=3)).complete
    assert len(accepted(executor, "refresh_requests")) == 2


def test_transaction_duplicates_corrections_and_out_of_order_arrivals():
    fixtures = SourceFixtures()
    fixtures.events *= 2
    executor = runner(fixtures)
    references(executor)
    assert executor.run(config("transactions")).complete
    assert len(accepted(executor, "transactions")) == 1
    fixtures.events = [transaction(description="Corrected signing"), transaction("older", day="2026-10-10", kind="Traded")]
    report = executor.run(config("transactions", mode="refresh"))
    assert report.complete
    assert len(executor.store.rows["dev", "transactions", ("usatoday", "sign-1")]) == 2
    assert len(accepted(executor, "refresh_requests")) == 2  # one per accepted revision
    fixtures.events = [transaction(description="Conflicting A"), transaction(description="Conflicting B")]
    report = executor.run(config("transactions", mode="refresh"))
    assert report.run.status == "failed" and "duplicate" in report.error
    assert latest(executor.store, "transactions", ("usatoday", "sign-1")).description == "Corrected signing"


def test_duplicate_transaction_revisions_use_source_update_time_and_retain_it():
    fixtures = SourceFixtures()
    old = {**transaction(description="Earlier revision"), "updatedAt": "2026-10-11T01:00:00Z"}
    new = {**transaction(description="Later revision"), "updatedAt": "2026-10-11T02:00:00Z"}
    fixtures.events = [new, old]
    executor = runner(fixtures)
    references(executor)
    assert executor.run(config("transactions")).complete
    assert latest(executor.store, "transactions", ("usatoday", "sign-1")).description == "Later revision"
    observation = next(row for row in accepted(executor, "source_observations") if row.dataset == "transactions")
    assert observation.source_updated_at.hour == 2
    assert observation.observed_at == NOW


def test_unresolved_vendor_ids_do_not_match_by_display_name_or_queue_refreshes():
    fixtures = SourceFixtures()
    fixtures.events = [transaction(player_ids=("unknown",))]
    executor = runner(fixtures)
    references(executor)
    report = executor.run(config("transactions"))
    assert report.run.counters.unresolved == 2
    assert not accepted(executor, "transactions") and not accepted(executor, "refresh_requests")
    assert accepted(executor, "validation_issues")
    assert accepted(executor, "source_observations")


def test_transaction_current_window_excludes_old_records_and_holds_truncation():
    fixtures = SourceFixtures()
    fixtures.events = [transaction("ancient", day="2009-10-11"), transaction()]
    executor = runner(fixtures)
    references(executor)
    assert executor.run(config("transactions")).complete
    assert [row.source_id for row in accepted(executor, "transactions")] == ["sign-1"]
    original = fixtures.transport
    def truncated(url, **kwargs):
        if "usatoday" in url:
            row = transaction()
            return Response(200, page([row], cursor=json.dumps([row["date"]["full"], row["id"]]), num_results=10000).encode())
        return original(url, **kwargs)
    executor.client.transport = truncated
    report = executor.run(config("transactions", mode="refresh"))
    assert report.run.status == "failed" and "truncates" in report.error
    assert not report.committed_cursors
    with pytest.raises(ValueError):
        config("transactions", mode="backfill")
    report = executor.run(config("transactions", mode="refresh", correction_lookback_days=32))
    assert report.run.status == "failed" and "policy" in report.error


def test_manual_override_precedence_and_expiration():
    executor = runner()
    assert setup(executor).complete
    override = RosterOverride(override_id=uuid4(), player_id=1001, status="LTIR", team_id=10,
        effective_from=date(2026, 10, 10), effective_to=date(2026, 10, 12), actor="reviewer", reason="Verified decision")
    seed(executor, "roster_overrides", override)
    assert executor.run(config("roster_reconciliation", mode="refresh")).complete
    assert latest(executor.store, "roster_state", (1001,)).override_id == override.override_id
    executor.now = lambda: NOW + timedelta(days=1)
    executor.store.now = NOW + timedelta(days=1)
    report = executor.run(config("roster_reconciliation", mode="refresh"))
    assert report.complete, (report.error, report.issues)
    snapshot = executor.store.snapshot("dev", accepted_before=NOW+timedelta(days=1))
    state = executor.store.get("roster_state", (1001,), snapshot=snapshot).write.decoded()
    assert state.status == "ACTIVE" and state.override_id is None


def test_ltir_transactions_survive_later_roster_fetches_and_uncertain_changes_are_held():
    fixtures = SourceFixtures()
    executor = runner(fixtures)
    assert setup(executor).complete
    fixtures.events = [transaction("ltir", day="2026-10-11", kind="Placed on long-term injured reserve")]
    assert executor.run(config("transactions", mode="refresh")).complete
    assert executor.run(config("roster_reconciliation", mode="refresh")).complete
    assert latest(executor.store, "roster_state", (1001,)).status == "LTIR"
    assert executor.run(config("team_rosters", mode="refresh")).complete
    assert executor.run(config("roster_reconciliation", mode="refresh")).complete
    assert latest(executor.store, "roster_state", (1001,)).status == "LTIR"
    fixtures.events = [transaction("unknown-status", day="2026-10-12", kind="Placed on injured reserve", description="AHL speculation")]
    assert executor.run(config("transactions", mode="refresh")).complete
    report = executor.run(config("roster_reconciliation", mode="refresh"))
    assert report.run.status == "failed" and report.issues
    assert latest(executor.store, "roster_state", (1001,)).status == "LTIR"


def test_contract_corrections_missing_coverage_and_invalid_money_preserve_last_terms():
    fixtures = SourceFixtures()
    executor = runner(fixtures)
    assert setup(executor).complete
    original = [row for row in accepted(executor, "contract_seasons") if row.player_id == 1001 and row.season == 2026][0]
    fixtures.contracts[1001] = contract_page(1001, cap_hit="$1,100,000")
    assert executor.run(config("contracts", mode="refresh")).complete
    corrected = latest(executor.store, "contract_seasons", (original.contract_id, 2026))
    assert corrected.cap_hit == 110000000
    fixtures.contracts[1001] = contract_page(1001, cap_hit="$1.001")
    report = executor.run(config("contracts", mode="refresh"))
    assert report.run.status == "failed" and not report.committed_cursors
    assert latest(executor.store, "contract_seasons", (original.contract_id, 2026)) == corrected
    fixtures.contracts[1001] = "No recorded contracts"
    report = executor.run(config("contracts", mode="refresh"))
    assert report.run.status == "failed" and "Unavailable required contract seasons" in report.error
    assert latest(executor.store, "contract_seasons", (original.contract_id, 2026)) == corrected


@pytest.mark.parametrize("body", ["<html>login required</html>", contract_page(1001, term=9), contract_page(1001).replace("2026-2027", "invalid"), contract_page(1001, cap_hit="NaN")])
def test_contract_parser_rejects_changed_partial_and_malformed_pages(body):
    with pytest.raises(ValueError):
        parse_capspace(body, 1001)


def test_contract_parser_rejects_mismatched_identity_and_prebaseline_agreements_keep_actual_term():
    with pytest.raises(ValueError, match="different NHL"):
        parse_capspace(contract_page(1002), 1001)
    agreements = parse_capspace(contract_page(1001, first=2007, last=2009), 1001)
    agreement = agreements[0]
    value = validate_record("contracts", {key: agreement[key] for key in ("start_season", "end_season", "term_years", "is_entry_level")} | {"contract_id": 1, "player_id": 1001})
    assert value.start_season == 2007 and value.term_years == 3


def test_identity_validated_explicit_capwages_fallback():
    fixtures = SourceFixtures()
    executor = runner(fixtures, mappings=(MappingCandidate("capwages", "player", "test-player", 1001, "reviewed NHL-ID link"),))
    references(executor)
    fixtures.status["/person/nhl:1001"] = 404
    person = {"nhlId": 1001, "contracts": [{"id": "fallback-1", "signingDate": "2025-07-01", "type": "Standard",
        "details": [{"season": f"{year}-{year+1}", "capHit": "$1,000,000"} for year in (2025, 2026, 2027)]}]}
    fixtures.capwages = '<script id="__NEXT_DATA__">'+json.dumps({"props": {"pageProps": {"player": person}}})+'</script>'
    assert executor.run(config("contracts", mode="refresh")).complete
    assert any("capwages.com/players/test-player" in url for url in fixtures.calls)
    person["nhlId"] = 1002
    with pytest.raises(ValueError, match="matching NHL"):
        parse_capwages('<script id="__NEXT_DATA__">'+json.dumps({"props": {"pageProps": {"player": person}}})+'</script>', 1001)


def test_conflicting_external_mapping_is_held_instead_of_reassigned():
    executor = runner()
    references(executor)
    from app.jobs.sources.nhl import operations
    executor.operations["source_id_mappings"] = operations(mappings=(MappingCandidate("usatoday", "player", "p1", 1002, "different reviewer claim"),))["source_id_mappings"]
    report = executor.run(config("source_id_mappings", mode="refresh"))
    assert report.run.status == "failed" and report.run.counters.unresolved == 1
    assert latest(executor.store, "source_mappings", ("usatoday", "player", "p1")).canonical_id == 1001


def test_empty_and_changed_transaction_pages_are_distinct():
    assert parse_page(page([])) == ([], None)
    with pytest.raises(ValueError):
        parse_page(page([], num_results=50))
    with pytest.raises(ValueError):
        parse_page('<script id="__NEXT_DATA__">{"props":{}}</script>')


def test_policy_bounds_and_game_data_operations_remain_deferred():
    for days in (0, 32, True):
        with pytest.raises(ValueError):
            TransactionPolicy(recent_days=days)
    with pytest.raises(ValueError):
        RosterPolicy(maximum_snapshot_age_days=32)
    assert set(core_operations()) == set(CORE)
    assert runner().run(config("game_schedule")).run.status == "deferred"


def test_recorded_public_source_formats_and_exact_units():
    from types import SimpleNamespace
    root = Path(__file__).parent / "fixtures/core_sources"
    agreement = parse_capspace((root/"capspace_current.html").read_text(), 8471214)[0]
    assert agreement["start_season"] == 2026 and agreement["terms"][0]["cap_hit"] == 425000000
    rows, cursor = parse_page((root/"usatoday_page.html").read_text())
    assert rows[0]["player"]["playerID"] == "1248145" and cursor
    for filename, kind in (("stats.json", "skater"), ("goalies.json", "goalie")):
        raw = json.loads((root/filename).read_text())["data"][0]
        profile = PlayerProfile(player_id=7, nhl_player_id=raw["playerId"], first_name="Test", last_name="Player", active=True)
        ctx = SimpleNamespace(find_unique=lambda *args: profile)
        item = SimpleNamespace(payload={"raw": raw, "season": 2025, "game_type": 2, "stat_kind": kind, "team_id": None})
        result = validate_record("basic_stats", normalize_stats(item, ctx))
        assert result.games_played == raw["gamesPlayed"]
        if kind == "goalie":
            assert result.time_on_ice == float(raw["timeOnIce"]) and result.save_percentage == raw["savePct"]


def test_interrupted_transaction_commit_rolls_back_fact_and_all_refresh_requests(monkeypatch):
    from .contract_store import ContractTransaction
    executor = runner()
    references(executor)
    original = ContractTransaction.commit
    def fail_transaction(transaction):
        if transaction.batch.checkpoint and transaction.batch.checkpoint.checkpoint.job == "transactions":
            transaction.store.fail_before_commit = True
            try:
                return original(transaction)
            finally:
                transaction.store.fail_before_commit = False
        return original(transaction)
    monkeypatch.setattr(ContractTransaction, "commit", fail_transaction)
    report = executor.run(config("transactions"))
    assert report.run.status == "failed" and not report.committed_cursors
    assert not accepted(executor, "transactions") and not accepted(executor, "refresh_requests")


def test_multi_participant_trade_requires_team_direction_then_reprocesses():
    fixtures = SourceFixtures()
    executor = runner(fixtures)
    assert setup(executor).complete
    trade = transaction("trade", ("p1", "p2"), day="2026-10-12", kind="Traded", team="t20")
    trade["fromTeam"] = {"teamID": "t10"}
    fixtures.events = [trade]
    assert executor.run(config("transactions", mode="refresh")).complete
    report = executor.run(config("roster_reconciliation", mode="refresh"))
    assert report.run.status == "failed" and "direction" in report.issues[0].message
    assert latest(executor.store, "roster_state", (1001,)).team_id == 10
    trade["players"][0]["role"] = "to_team"
    trade["players"][1]["role"] = "from_team"
    assert executor.run(config("transactions", mode="refresh")).complete
    assert executor.run(config("roster_reconciliation", mode="refresh")).complete
    assert latest(executor.store, "roster_state", (1001,)).team_id == 20
    assert latest(executor.store, "roster_state", (1002,)).team_id == 10


def test_late_older_transaction_cannot_rewind_a_later_activation():
    fixtures = SourceFixtures()
    executor = runner(fixtures)
    assert setup(executor).complete
    fixtures.events = [transaction("activated", day="2026-10-11", kind="Activated from long-term injured reserve")]
    assert executor.run(config("transactions", mode="refresh")).complete
    assert executor.run(config("roster_reconciliation", mode="refresh")).complete
    before = latest(executor.store, "roster_state", (1001,))
    fixtures.events = [transaction("older-ltir", day="2026-10-10", kind="Placed on long-term injured reserve")]
    assert executor.run(config("transactions", mode="refresh")).complete
    assert executor.run(config("roster_reconciliation", mode="refresh")).complete
    assert latest(executor.store, "roster_state", (1001,)) == before


def test_stale_or_incomplete_roster_evidence_and_conflicting_overrides_preserve_state():
    executor = runner(roster_policy=RosterPolicy(maximum_snapshot_age_days=0))
    assert setup(executor).complete
    before = latest(executor.store, "roster_state", (1001,))
    executor.now = lambda: NOW + timedelta(days=1)
    executor.store.now = NOW + timedelta(days=1)
    report = executor.run(config("roster_reconciliation", mode="refresh"))
    assert report.run.status == "failed" and "fresh" in report.issues[0].message
    assert latest(executor.store, "roster_state", (1001,)) == before
    executor.now = lambda: NOW
    for _ in range(2):
        seed(executor, "roster_overrides", RosterOverride(override_id=uuid4(), player_id=1001,
            status="LTIR", effective_from=date(2026, 10, 10), reason="Verified", actor="Reviewer"))
    report = executor.run(config("roster_reconciliation", mode="refresh"))
    assert report.run.status == "failed" and "Overlapping" in report.issues[0].message


def test_references_include_teams_before_their_first_current_season_game():
    fixtures = SourceFixtures()
    fixtures.mutate = lambda path, data: {"data": [], "total": 0} if path.endswith("team/summary") else data
    executor = runner(fixtures)
    assert executor.run(config("teams_seasons")).complete
    assert all(team.active for team in accepted(executor, "teams"))
    assert len(accepted(executor, "team_seasons")) == 2


def test_preseason_summary_and_wrong_landing_identity_cannot_be_accepted():
    fixtures = SourceFixtures()
    def preseason(path, data):
        if path.endswith("skater/summary"):
            data["data"] = [{**row, "gameTypeId": 1} for row in data["data"]]
        return data
    fixtures.mutate = preseason
    executor = runner(fixtures)
    assert executor.run(config("player_profiles")).run.status == "failed"
    assert not accepted(executor, "player_profiles")
    fixtures.mutate = lambda path, data: {**data, "playerId": 999} if path.endswith("/landing") else data
    report = executor.run(config("player_profiles"))
    assert report.run.status == "failed" and "different NHL identity" in report.error


def test_traded_player_team_rows_do_not_duplicate_source_total():
    from urllib.parse import parse_qs, urlparse
    fixtures = SourceFixtures()
    original = fixtures.transport
    def traded(url, **kwargs):
        response = original(url, **kwargs)
        if "/skater/summary" not in url:
            return response
        exp = parse_qs(urlparse(url).query)["cayenneExp"][0]
        data = json.loads(response.body)
        if "teamId=20" in exp:
            data["data"] = [{**row, "playerId": 1001} for row in data["data"]]
        elif "teamId=" not in exp:
            data["data"] = [{**row, "gamesPlayed": 20, "goals": 4, "assists": 6, "points": 10, "shots": 40}
                            if row["playerId"] == 1001 else row for row in data["data"]]
        return Response(200, json.dumps(data).encode())
    fixtures.transport = traded
    executor = runner(fixtures)
    references(executor)
    rows = [row for row in accepted(executor, "basic_stats") if row.player_id == 1001 and row.season == 2026]
    assert [(row.games_played, row.team_id) for row in rows if row.team_scope == "TOTAL"] == [(20, None)]
    assert {row.team_id for row in rows if row.team_scope == "TEAM"} == {10, 20}


def test_source_resume_rejects_changed_enumeration_then_reprocesses_without_resume():
    from .contract_store import ContractTransaction
    from unittest.mock import patch
    fixtures = SourceFixtures()
    executor = runner(fixtures)
    original = ContractTransaction.commit
    def interrupt(transaction):
        checkpoint = transaction.batch.checkpoint
        if checkpoint and checkpoint.checkpoint.job == "player_profiles" and checkpoint.checkpoint.cursor["position"]["offset"] == 2:
            raise RuntimeError("Interrupted source upload")
        return original(transaction)
    with patch.object(ContractTransaction, "commit", interrupt):
        report = executor.run(config("player_profiles", max_batch_records=1))
    assert report.run.status == "partial" and len(accepted(executor, "player_profiles")) == 1
    fixtures.mutate = lambda path, data: {**data, "firstName": {"default": "Corrected"}} if path.endswith("/landing") else data
    changed = executor.run(config("player_profiles", max_batch_records=1, resume=True))
    assert changed.run.status == "failed" and "enumeration changed" in changed.error
    assert len(accepted(executor, "player_profiles")) == 1
    fixtures.mutate = lambda path, data: data
    assert executor.run(config("player_profiles", max_batch_records=1, resume=True)).complete
    assert len(accepted(executor, "player_profiles")) == 2
    fixtures.mutate = lambda path, data: {**data, "firstName": {"default": "Corrected"}} if path.endswith("/landing") else data
    assert executor.run(config("player_profiles", max_batch_records=1)).complete
    assert latest(executor.store, "player_profiles", (1001,)).first_name == "Corrected"


def test_canonical_id_collision_cannot_overwrite_an_unrelated_player():
    executor = runner()
    profile = PlayerProfile(player_id=1001, nhl_player_id=9001, first_name="Existing", last_name="Identity", active=True)
    seed(executor, "player_profiles", profile)
    report = executor.run(config("player_profiles"))
    assert report.run.status == "failed" and "collides" in report.error
    assert latest(executor.store, "player_profiles", (1001,)) == profile


@pytest.mark.parametrize("path", ["/team", "/season", "/franchise"])
def test_duplicate_reference_source_ids_are_not_silently_collapsed(path):
    fixtures = SourceFixtures()
    fixtures.mutate = lambda url, data: {"data": [*data["data"], data["data"][0]], "total": data["total"]+1} if url.endswith(path) else data
    executor = runner(fixtures)
    report = executor.run(config("teams_seasons"))
    assert report.run.status == "failed" and "Duplicate NHL reference" in report.error
    assert not accepted(executor, "teams")


def test_unknown_optional_franchise_is_null_and_cannot_erase_an_existing_link():
    fixtures = SourceFixtures()
    fixtures.mutate = lambda path, data: {**data, "data": [{**row, "franchiseId": None} for row in data["data"]]} if path.endswith("/team") else data
    executor = runner(fixtures)
    assert executor.run(config("teams_seasons")).complete
    assert all(row.franchise_id is None for row in accepted(executor, "teams"))
    fixtures.mutate = lambda path, data: data
    assert executor.run(config("teams_seasons", mode="refresh")).complete
    fixtures.mutate = lambda path, data: {**data, "data": [{**row, "franchiseId": None} for row in data["data"]]} if path.endswith("/team") else data
    assert executor.run(config("teams_seasons", mode="refresh")).complete
    assert latest(executor.store, "teams", (10,)).franchise_id == 10

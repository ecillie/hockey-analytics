"""Coverage gates for incomplete sources, historical gaps, and optional feeds."""

from copy import deepcopy

import pytest

from app.jobs.shared.coverage import (
    DATASET_POLICIES,
    POLICY_VERSION,
    CoverageObservation,
    CoveragePartition,
    assess_coverage,
    check_record_coverage,
)


def report(partition, **changes):
    evidence = dict(expected_records=10, accepted_records=10, collection_complete=True)
    evidence.update(changes)
    return assess_coverage(
        [partition], [CoverageObservation(partition, **evidence)], current_season=2026
    )


def test_required_salary_gaps_block_completion_and_remain_visible_by_season():
    historical = CoveragePartition("contract_seasons", 2008)
    current = CoveragePartition("contract_seasons", 2026)
    result = assess_coverage(
        [current, historical],
        [CoverageObservation(current, 12, 12, True), CoverageObservation(historical, 10, 8, True)],
        current_season=2026,
    )
    assert not result.complete
    assert result.policy_version == POLICY_VERSION
    assert result.requested == (current, historical)
    assert [(issue.partition, issue.code, issue.blocking) for issue in result.issues] == [
        (historical, "MISSING_RECORDS", True)
    ]


def test_optional_edge_events_do_not_hide_required_edge_summary_failures():
    summaries = CoveragePartition("edge_summaries", 2021, 2)
    events = CoveragePartition("edge_events", 2021, 2)
    result = assess_coverage([summaries, events], [], current_season=2026)
    assert not result.complete
    assert [issue.blocking for issue in result.issues] == [True, False]


def test_optional_unavailable_feeds_are_reported_without_blocking_required_coverage():
    events = CoveragePartition("edge_events", 2021, 3)
    result = report(events, expected_records=None, accepted_records=0,
                    collection_complete=False, unavailable_reason="No historical event feed")
    assert result.complete
    assert {issue.code for issue in result.issues} == {
        "UNAVAILABLE", "INCOMPLETE_COLLECTION", "UNKNOWN_EXPECTED_COUNT"
    }
    assert all(not issue.blocking for issue in result.issues)


@pytest.mark.parametrize("changes, code", [
    ({"expected_records": None}, "UNKNOWN_EXPECTED_COUNT"),
    ({"collection_complete": False}, "INCOMPLETE_COLLECTION"),
    ({"invalid_records": 2}, "INVALID_RECORDS"),
    ({"unresolved_records": 1}, "UNRESOLVED_IDENTITIES"),
    ({"missing_required_fields": ("game_id",)}, "MISSING_REQUIRED_FIELDS"),
    ({"unavailable_reason": "Source access failed"}, "UNAVAILABLE"),
])
def test_a_successful_fetch_or_matching_row_count_does_not_override_other_gaps(changes, code):
    result = report(CoveragePartition("games", 2026, 2), **changes)
    assert not result.complete
    assert [issue.code for issue in result.issues] == [code]


def test_verified_empty_population_is_valid_without_fixed_season_volume_assumptions():
    assert report(CoveragePartition("game_stats", 2026, 3),
                  expected_records=0, accepted_records=0).complete


def test_unknown_empty_population_cannot_be_reported_as_complete():
    assert not report(CoveragePartition("game_stats", 2026, 3),
                      expected_records=None, accepted_records=0).complete


@pytest.mark.parametrize("dataset, record, required, optional", [
    ("contract_seasons", {"contract_id": 1, "player_id": 7, "season": 2008, "cap_hit": 0,
                          "base_salary": None, "signing_bonus": 0}, (),
     ("base_salary", "performance_bonus", "total_cash", "owning_team_id")),
    ("player_profiles", {"player_id": 7, "first_name": "  ", "last_name": "Player"},
     ("first_name",), ("birth_date", "position", "nationality", "shoots_catches")),
    ("transactions", {"source_id": "a", "event_date": "2026-10-10", "event_type": "signed", "participants": []},
     ("participants",), ("description", "from_team_id", "to_team_id")),
    ("edge_summaries", {"entity_id": 7, "entity_type": "player", "season": 2021,
                        "game_type": 2, "metrics": {}, "observed_at": "2026-10-10T12:00:00Z"},
     ("metrics",), ("breakdowns",)),
])
def test_missing_fields_are_reported_without_fabricating_or_mutating_values(dataset, record, required, optional):
    before = deepcopy(record)
    result = check_record_coverage(dataset, record)
    assert result.missing_required == required
    assert result.missing_optional == optional
    assert result.valid == (not required)
    assert record == before


@pytest.mark.parametrize("participants", [[], (), {}, set(), frozenset()])
def test_empty_participant_collections_cannot_establish_transaction_coverage(participants):
    result = check_record_coverage("transactions", {
        "source_id": "a", "event_date": "2026-10-10", "event_type": "signed",
        "participants": participants,
    })
    assert not result.valid
    assert result.missing_required == ("participants",)


@pytest.mark.parametrize("partition, mode", [
    (CoveragePartition("games", 2026, 1), "initial"),
    (CoveragePartition("shots", 2026, 1), "refresh"),
    (CoveragePartition("edge_summaries", 2020, 2), "initial"),
    (CoveragePartition("basic_stats", 2007, 2), "backfill"),
    (CoveragePartition("games", 2027, 2), "initial"),
    (CoveragePartition("games", 2026), "initial"),
    (CoveragePartition("games", True, 2), "initial"),
    (CoveragePartition("games", 2026, True), "initial"),
    (CoveragePartition("teams", 2026), "initial"),
    (CoveragePartition("transactions"), "backfill"),
    (CoveragePartition("transactions", 2026), "initial"),
    (CoveragePartition("contract_seasons", 2026, 2), "initial"),
])
def test_disallowed_collection_scopes_are_rejected_before_assessing_coverage(partition, mode):
    with pytest.raises(ValueError):
        assess_coverage([partition], [], current_season=2026, mode=mode)


def test_published_future_contract_terms_do_not_enable_future_game_seasons():
    assert report(CoveragePartition("contract_seasons", 2030)).complete


def test_current_transaction_processing_is_allowed_without_a_historical_partition():
    for mode in ("initial", "refresh"):
        partition = CoveragePartition("transactions")
        assert assess_coverage([partition], [CoverageObservation(partition, 3, 3, True)],
                               current_season=2026, mode=mode).complete


@pytest.mark.parametrize("requested, observed", [
    ([], []),
    ([CoveragePartition("teams"), CoveragePartition("teams")], []),
    ([CoveragePartition("teams")], [CoverageObservation(CoveragePartition("player_profiles"), 1, 1, True)]),
    ([CoveragePartition("teams")], [CoverageObservation(CoveragePartition("teams"), 1, 1, True)] * 2),
])
def test_empty_duplicate_or_unrequested_evidence_cannot_produce_a_valid_gate(requested, observed):
    with pytest.raises(ValueError):
        assess_coverage(requested, observed, current_season=2026)


@pytest.mark.parametrize("changes", [
    {"accepted_records": -1}, {"expected_records": -1}, {"invalid_records": -1},
    {"unresolved_records": -1}, {"accepted_records": 1.5}, {"expected_records": True},
    {"accepted_records": 11}, {"collection_complete": "yes"},
])
def test_malformed_evidence_is_rejected(changes):
    with pytest.raises(ValueError):
        report(CoveragePartition("teams"), **changes)


@pytest.mark.parametrize("current_season, mode", [(True, "initial"), (2007, "initial"), (2026, "daily")])
def test_invalid_run_configuration_is_rejected(current_season, mode):
    with pytest.raises(ValueError):
        assess_coverage([CoveragePartition("teams")], [], current_season=current_season, mode=mode)


def test_unknown_dataset_cannot_silently_skip_requirements():
    with pytest.raises(KeyError):
        report(CoveragePartition("unknown"))


@pytest.mark.parametrize("dataset", ["ahl_roster_evidence", "shot_summaries"])
def test_excluded_datasets_cannot_be_requested_or_accepted(dataset):
    with pytest.raises(KeyError):
        report(CoveragePartition(dataset))
    with pytest.raises(KeyError):
        check_record_coverage(dataset, {})


def test_policy_cannot_be_changed_by_a_single_job():
    with pytest.raises(TypeError):
        DATASET_POLICIES["teams"] = DATASET_POLICIES["edge_events"]

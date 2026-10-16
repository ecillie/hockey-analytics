from copy import deepcopy
from datetime import date, datetime, timezone
import json
from pathlib import Path

import pytest

from app.jobs.shared.coverage import DATASET_POLICIES, check_record_coverage
from app.jobs.shared.data_contracts import RECORD_DEFINITIONS, validate_batch, validate_record


FIXTURES = json.loads((Path(__file__).parent / "fixtures/data_contracts/records.json").read_text())


def record(family, **changes):
    payload = deepcopy(FIXTURES[family][0])
    payload.update(changes)
    return validate_record(family, json.dumps(payload))


def records():
    return tuple((dataset, validate_record(dataset, json.dumps(payload)))
                 for dataset, rows in FIXTURES.items() for payload in rows)


@pytest.mark.parametrize("dataset", RECORD_DEFINITIONS)
def test_every_record_family_has_a_valid_fixture_and_key(dataset):
    value = record(dataset)
    assert RECORD_DEFINITIONS[dataset].key(value)
    assert validate_record(dataset, value.model_dump()) == value
    assert validate_record(dataset, value.model_dump_json()) == value


def test_every_coverage_output_has_a_logical_contract():
    assert set(DATASET_POLICIES) <= set(RECORD_DEFINITIONS)
    assert set(RECORD_DEFINITIONS) == set(FIXTURES)
    for dataset in DATASET_POLICIES:
        assert not check_record_coverage(dataset, record(dataset).model_dump()).missing_required
    assert not {"ahl", "shot_summaries"} & set(RECORD_DEFINITIONS)


def test_relationship_fixture_graph_resolves_without_a_database():
    validate_batch(records(), lambda *_: None)


@pytest.mark.parametrize(("dataset", "changes"), [
    ("teams", {"team_id": True}), ("teams", {"active": 1}),
    ("teams", {"name": "  "}), ("teams", {"unexpected_column": 1}),
    ("contract_seasons", {"cap_hit": "800000000"}),
    ("contract_seasons", {"cap_hit": 800000000.5}),
    ("contract_seasons", {"cap_hit": -1}), ("contract_seasons", {"cap_hit": True}),
    ("basic_stats", {"points": 0}), ("basic_stats", {"team_id": 10}),
    ("basic_stats", {"team_scope": "TEAM"}), ("basic_stats", {"game_type": 1}),
    ("basic_stats", {"game_type": 2.0}),
    ("basic_stats", {"season": 2007}), ("basic_stats", {"shooting_percentage": 15}),
    ("basic_stats", {"shots_against": 10, "saves": 11}),
    ("seasons", {"end_year": 2027}), ("contracts", {"term_years": 2}),
    ("contracts", {"end_season": 2024}),
    ("memberships", {"effective_from": "2025-12-01", "effective_to": "2025-10-01"}),
    ("games", {"away_team_id": 10}), ("games", {"start_time": "2025-10-10T19:00:00"}),
    ("moneypuck_skater_stats", {"game_score": float("inf")}),
    ("moneypuck_skater_stats", {"expected_goals": float("nan")}),
    ("game_events", {"y": None}), ("shots", {"coordinate_system": None}),
    ("edge_summaries", {"season": 2020}), ("edge_summaries", {"metrics": {}}),
    ("moneypuck_line_stats", {"player_ids": [7, 7]}),
    ("transactions", {"participants": [{"player_id": 7}, {"player_id": 7}]}),
    ("transactions", {"participants": []}),
    ("pipeline_runs", {"counters": {"read": 1, "accepted": 2}}),
    ("pipeline_runs", {"finished_at": None}),
    ("pipeline_runs", {"finished_at": "2026-10-10T11:00:00Z"}),
    ("pipeline_runs", {"status": "running"}),
    ("validation_issues", {"disposition": "resolved"}),
    ("source_observations", {"dataset": "ahl"}),
    ("source_observations", {"content_digest": "no digest"}),
    ("source_observations", {"payload": {"bad": float("inf")}}),
])
def test_invalid_source_values_are_held_instead_of_coerced(dataset, changes):
    with pytest.raises(ValueError):
        record(dataset, **changes)


def test_unknown_and_zero_remain_distinct_and_dates_are_not_fabricated():
    value = record("basic_stats", goals=0, assists=None, points=None)
    assert value.goals == 0 and value.assists is None
    assert record("memberships").effective_from is None
    assert record("games").start_time == datetime(2025, 10, 10, 23, tzinfo=timezone.utc)
    assert record("transactions").event_date == date(2026, 10, 9)
    assert record("moneypuck_line_stats").player_ids == (7, 8)


def test_source_observations_do_not_share_mutable_input():
    payload = deepcopy(FIXTURES["source_observations"][0])
    value = validate_record("source_observations", json.dumps(payload))
    payload["payload"]["player_id"] = 999
    assert value.payload["player_id"] == 1007


@pytest.mark.parametrize(("dataset", "changes", "message"), [
    ("contract_seasons", {"player_id": 8}, "owner or range"),
    ("contract_seasons", {"season": 2024}, "Unresolved reference"),
    ("shots", {"team_id": 99}, "Unresolved reference"),
    ("shots", {"game_type": 3}, "season/type"),
    ("game_stats", {"entity_type": "team", "entity_id": 11}, "differs from its team"),
    ("source_mappings", {"canonical_id": 999}, "Unresolved reference"),
    ("roster_state", {"override_id": "00000000-0000-0000-0000-000000000002"}, "differs from its override"),
])
def test_invalid_relationships_block_the_batch(dataset, changes, message):
    batch = tuple((name, value) for name, value in records() if name != dataset)
    with pytest.raises(ValueError, match=message):
        validate_batch(batch + ((dataset, record(dataset, **changes)),), lambda *_: None)


def test_duplicate_natural_and_source_identities_block_acceptance():
    with pytest.raises(ValueError, match="Duplicate record identity"):
        validate_batch(records() + (("basic_stats", record("basic_stats")),), lambda *_: None)
    with pytest.raises(ValueError, match="Duplicate source identity"):
        validate_batch(records() + (("games", record("games", game_id=2)),), lambda *_: None)


def test_lookup_must_return_the_requested_identity():
    with pytest.raises(ValueError, match="different record identity"):
        validate_batch((("memberships", record("memberships")),), lambda *_: record("teams"))


def test_model_construct_cannot_bypass_acceptance():
    unsafe = record("contract_seasons").model_copy(update={"cap_hit": -1})
    with pytest.raises(ValueError):
        validate_batch((("contract_seasons", unsafe),), lambda *_: None)
    with pytest.raises(ValueError, match="model does not match"):
        validate_batch((("teams", record("player_profiles")),), lambda *_: None)


def test_dataset_inputs_require_known_keys_and_distinct_pinned_revisions():
    item = deepcopy(FIXTURES["datasets"][0]["input_revisions"][0])
    for values in ([dict(item, dataset="ahl")], [dict(item, record_key=[7])], [item, item]):
        with pytest.raises(ValueError):
            record("datasets", input_revisions=values)


def test_roster_override_requires_supported_identity_and_interval():
    revised = record("roster_state", status="LTIR", override_id="00000000-0000-0000-0000-000000000002")
    batch = tuple((name, value) for name, value in records() if name != "roster_state")
    validate_batch(batch + (("roster_state", revised),), lambda *_: None)
    with pytest.raises(ValueError, match="outside its override interval"):
        validate_batch(batch + (("roster_state", record("roster_state", status="LTIR", effective_date="2026-10-09", override_id=str(revised.override_id))),), lambda *_: None)

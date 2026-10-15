from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import uuid4

import pytest

from app.jobs.dataset_processing import DatasetDefinition, INPUTS, build_dataset, dataset_operation
from app.jobs.shared.access_contracts import StoredRecord, make_write
from app.jobs.shared.execution import Executor
from app.jobs.shared.cli import report_exit_code
from app.jobs.shared.data_contracts import canonical_json, validate_record
from database.pipeline.artifacts import LocalArtifacts
from .test_data_contracts import record
from .execution_fixtures import config
from .contract_store import ContractStore

CUTOFF = datetime(2026, 10, 14, tzinfo=timezone.utc)
DEFINITION = DatasetDefinition(dataset_id="skater-performance", train_through=2022, validation_season=2023, test_season=2024,
    expected_player_seasons=tuple((player, year) for year in range(2020,2025) for player in (7,8)), coverage_audit="fixture independent participation manifest")


def fixture_inputs(kind="skater"):
    result = {name: [] for name in INPUTS}

    def append(dataset, value):
        result[dataset].append(StoredRecord(write=make_write(dataset, value, expected_revision=None),
            revision=1, accepted_at=datetime(2026,10,10,tzinfo=timezone.utc), run_id=uuid4()))

    for player in (7, 8):
        append("player_profiles", record("player_profiles", player_id=player, nhl_player_id=1000+player,
            position="G" if kind == "goalie" else "C"))
    for year in range(2020, 2025):
        append("seasons", record("seasons", season=year, end_year=year+1, label=f"{year}-{year+1}"))
        for player in (7, 8):
            append("basic_stats", record("basic_stats", source="nhl", player_id=player,
                season=year, stat_kind=kind))
            dataset = "moneypuck_skater_stats" if kind == "skater" else "moneypuck_goalie_stats"
            kwargs = {"source": "moneypuck", "player_id": player, "season": year,
                      "ice_time": 36000.0 if player == 7 else 72000.0}
            if kind == "skater":
                kwargs["game_score"] = 20.0 if player == 7 else 100.0
            append(dataset, record(dataset, **kwargs))
    return result


def build(inputs=None, definition=DEFINITION, **changes):
    return build_dataset(definition, inputs or fixture_inputs(), cutoff=CUTOFF, first_season=2020,
        last_season=2023, **changes)


def test_reproducible_bytes_pins_targets_nulls_and_time_ordering():
    inputs = fixture_inputs()
    first, second = build(inputs), build(inputs)
    assert first == second
    rows = json.loads(first.payload)["rows"]
    assert len(rows) == 8
    assert len({(row["player_id"], row["season"]) for row in rows}) == 8
    assert {row["target_season"] for row in rows if row["split"] == "train"} == {2021,2022}
    assert {row["target_season"] for row in rows if row["split"] == "validation"} == {2023}
    assert {row["target_season"] for row in rows if row["split"] == "test"} == {2024}
    assert all(row["season"] < row["target_season"] for row in rows)
    assert next(row for row in rows if row["player_id"] == 8)["target_hockey_value"] == pytest.approx(60.0)
    assert first.manifest.content_digest == sha256(first.payload).hexdigest()
    assert first.manifest.point_in_time_supported is False
    assert all(pin.revision == 1 for pin in first.manifest.input_revisions)
    assert not any("contract" in field or field == "cap_hit" for field in rows[0])
    # Reversing database page order cannot change bytes or manifest ordering.
    reversed_inputs = {name: list(reversed(rows)) for name, rows in inputs.items()}
    assert build(reversed_inputs) == first


def test_correction_changes_version_but_pinned_original_stays_reproducible():
    inputs = fixture_inputs()
    original = build(inputs)
    old = inputs["moneypuck_skater_stats"][0]
    value = old.write.decoded().model_copy(update={"game_score": 25.0})
    changed = StoredRecord(write=make_write("moneypuck_skater_stats", value, expected_revision=1),
        revision=2, accepted_at=old.accepted_at, run_id=old.run_id)
    corrected = {**inputs, "moneypuck_skater_stats": [changed, *inputs["moneypuck_skater_stats"][1:]]}
    assert build(corrected).manifest.version != original.manifest.version
    assert build(inputs) == original


@pytest.mark.parametrize("failure", ("duplicate", "missing_advanced", "missing_cap", "missing_profile", "missing_target", "late_revision", "missing_game_score"))
def test_quality_gates_block_invalid_publication(failure):
    inputs = fixture_inputs()
    if failure == "duplicate":
        inputs["basic_stats"].append(inputs["basic_stats"][0])
    elif failure == "missing_advanced":
        inputs["moneypuck_skater_stats"].pop(0)
    elif failure == "missing_cap":
        old = inputs["seasons"][0]
        inputs["seasons"][0] = old.model_copy(update={"write": make_write("seasons", old.write.decoded().model_copy(update={"salary_cap": None}), expected_revision=None)})
    elif failure == "missing_profile":
        inputs["player_profiles"].pop(0)
    elif failure == "missing_target":
        inputs["basic_stats"] = [row for row in inputs["basic_stats"] if row.write.decoded().season != 2024]
    elif failure == "late_revision":
        inputs["basic_stats"][0] = inputs["basic_stats"][0].model_copy(update={"accepted_at": datetime(2027,1,1,tzinfo=timezone.utc)})
    else:
        old = inputs["moneypuck_skater_stats"][0]
        inputs["moneypuck_skater_stats"][0] = old.model_copy(update={"write": make_write("moneypuck_skater_stats", old.write.decoded().model_copy(update={"game_score": None}), expected_revision=None)})
    with pytest.raises(ValueError):
        build(inputs)


def test_goalie_dataset_has_separate_performance_and_no_skater_contract_features():
    definition = DEFINITION.model_copy(update={"kind": "goalie", "dataset_id": "goalie-performance"})
    built = build(fixture_inputs("goalie"), definition)
    assert built.manifest.row_count == 8
    assert "expected_goals_against - goals_against" == built.manifest.feature_definitions["performance"]


def test_immutable_artifact_storage_validates_digest_and_rejects_path_escape(tmp_path):
    artifacts = LocalArtifacts(tmp_path)
    payload = build().payload
    digest = artifacts.put(payload)
    assert artifacts.put(payload) == digest
    assert artifacts.read(digest) == payload
    with pytest.raises(ValueError):
        artifacts.read("../secret")
    (tmp_path / (digest + ".json")).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="digest"):
        artifacts.read(digest)


def test_dataset_job_validation_only_does_not_write_artifacts_and_missing_config_defers(tmp_path):
    fixtures = tuple((name,row.write.decoded()) for name,rows in fixture_inputs().items() for row in rows)
    store = ContractStore(fixtures)
    executor = Executor(store, {"datasets": dataset_operation((DEFINITION,), LocalArtifacts(tmp_path), cutoff=CUTOFF)}, target_environment="dev", now=lambda:CUTOFF)
    scope = config("datasets", first_season=2020, last_season=2023, current_season=2026, mode="validation")
    assert executor.run(scope).complete
    assert not list(tmp_path.iterdir())
    executor.operations = {}
    report = executor.run(scope)
    assert report.run.status == "deferred" and report_exit_code(report) == 3
    assert report_exit_code(executor.run(scope.model_copy(update={"enabled": False}))) == 4


def test_total_precedence_stint_aggregation_and_missingness_preserve_zero():
    from app.jobs.dataset_processing import _total
    total = record("basic_stats", source="nhl", shots=0, goals=0, assists=0, points=0)
    stint = record("basic_stats", source="nhl", team_scope="TEAM", team_id=10)
    assert _total([total, stint], ("shots", "goals")) == {"shots":0,"goals":0}
    missing = record("basic_stats", source="nhl", team_scope="TEAM", team_id=20, shots=None)
    assert _total([stint, missing], ("shots",))["shots"] is None


def test_unknown_stat_provider_cannot_establish_the_required_dataset_population():
    inputs = fixture_inputs()
    inputs["basic_stats"] = [row.model_copy(update={"write":make_write("basic_stats",
        row.write.decoded().model_copy(update={"source":"unapproved-provider"}),expected_revision=None)}) for row in inputs["basic_stats"]]
    with pytest.raises(ValueError, match="No eligible"):
        build(inputs)


def test_dataset_ids_are_distinct_within_one_requested_build(tmp_path):
    with pytest.raises(ValueError, match="distinct IDs"):
        dataset_operation((DEFINITION,DEFINITION),LocalArtifacts(tmp_path))

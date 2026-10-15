"""Reproducible player-season datasets over pinned accepted revisions.

These are retrospectively assembled datasets. Acceptance-time snapshots prevent
later corrections leaking into a rerun; they do not establish historical source
availability at an old prediction date. No model is trained or activated here.
"""
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from math import isfinite

from pydantic import Field, StrictInt, model_validator

from .shared.access_contracts import ReadRequest
from .shared.data_contracts import DatasetVersion, Id, InputRevision, Record, Season, Text, RECORD_DEFINITIONS, canonical_json
from .shared.execution import JobOperation
from .sources.common import batches, source_record

TRANSFORMATION = "player-season-1"
INPUTS = ("player_profiles", "seasons", "basic_stats", "moneypuck_skater_stats", "moneypuck_goalie_stats")


class DatasetDefinition(Record):
    dataset_id: Text
    kind: str = "skater"
    train_through: Season
    validation_season: Season
    test_season: Season
    min_games: StrictInt = Field(default=20, ge=1)
    expected_player_seasons: tuple[tuple[Id, Season], ...] = Field(min_length=1)
    coverage_audit: Text

    @model_validator(mode="after")
    def policy(self):
        if self.kind not in ("skater", "goalie") or not self.train_through < self.validation_season < self.test_season:
            raise ValueError("Dataset requires a supported kind and time-ordered, disjoint splits")
        if len(set(self.expected_player_seasons)) != len(self.expected_player_seasons):
            raise ValueError("Dataset expected population contains duplicate identities")
        return self


@dataclass(frozen=True)
class BuiltDataset:
    manifest: DatasetVersion
    payload: bytes


def read_inputs(reader, snapshot):
    result = {}
    for dataset in INPUTS:
        rows, cursor = [], None
        while True:
            page = reader.scan(ReadRequest(dataset=dataset, snapshot=snapshot, cursor=cursor))
            rows.extend(page.records)
            cursor = page.next_cursor
            if cursor is None:
                break
        result[dataset] = rows
    return result


def _total(rows, fields, *, weighted=()):
    totals = [row for row in rows if row.team_scope == "TOTAL"]
    if len(totals) > 1:
        raise ValueError("Duplicate TOTAL rows at the dataset grain")
    selected = totals or rows
    if len({row.team_id for row in selected}) != len(selected):
        raise ValueError("Duplicate team stints at the dataset grain")
    result = {}
    for field in fields:
        values = [getattr(row, field) for row in selected]
        # Incomplete totals remain unknown; measured zeros stay zero.
        if any(value is None for value in values):
            result[field] = None
        elif field in weighted:
            denominator = sum(row.ice_time for row in selected)
            result[field] = sum(getattr(row, field) * row.ice_time for row in selected) / denominator if denominator else None
        else:
            result[field] = sum(values)
    return result


def build_dataset(definition, inputs, *, cutoff, first_season, last_season):
    if not first_season < definition.train_through < definition.validation_season < definition.test_season <= last_season + 1:
        raise ValueError("Dataset scope must include train, validation, and test seasons")
    used = {}

    def retain(dataset, stored):
        if stored.accepted_at > cutoff:
            raise ValueError("Input was accepted after the dataset cutoff")
        used[dataset, stored.write.payload, stored.revision] = (dataset, stored)
        return stored.write.decoded()

    profiles = {row.write.decoded().player_id: row for row in inputs["player_profiles"]}
    seasons = {row.write.decoded().season: row for row in inputs["seasons"]}
    basic, advanced = {}, {}
    for row in inputs["basic_stats"]:
        value = row.write.decoded()
        if (value.game_type == 2 and value.stat_kind == definition.kind
                and value.source.lower() in ("nhl", "cap space")
                and first_season <= value.season <= last_season + 1):
            basic.setdefault((value.player_id, value.season), []).append(row)
    advanced_name = "moneypuck_skater_stats" if definition.kind == "skater" else "moneypuck_goalie_stats"
    for row in inputs[advanced_name]:
        value = row.write.decoded()
        if value.game_type == 2 and value.situation == "all" and value.source.lower() == "moneypuck" and first_season <= value.season <= last_season + 1:
            advanced.setdefault((value.player_id, value.season), []).append(row)
    player_seasons = {}
    for key, candidates in sorted(basic.items()):
        # Match the SQL consumer source precedence before choosing TOTAL/stints.
        sources = {row.write.decoded().source for row in candidates}
        source = min(sources, key=lambda value: ({"nhl": 0, "cap space": 1}.get(value.lower(), 2), value))
        basic_rows = [retain("basic_stats", row) for row in candidates if row.write.decoded().source == source]
        bfields = ("games_played", "goals", "assists", "points", "shots") if definition.kind == "skater" else ("games_played", "saves", "shots_against", "goals_against")
        traditional = _total(basic_rows, bfields)
        if traditional["games_played"] < definition.min_games:
            continue
        if key not in advanced:
            raise ValueError("Required advanced inputs missing for an eligible player-season")
        arows = [retain(advanced_name, row) for row in advanced[key]]
        afields = ("ice_time", "game_score", "expected_goals", "on_ice_expected_goals_pct") if definition.kind == "skater" else ("ice_time", "expected_goals_against", "goals_against")
        metrics = _total(arows, afields, weighted=("on_ice_expected_goals_pct",))
        if metrics["ice_time"] is None or metrics["ice_time"] <= 0 or (definition.kind == "skater" and metrics["game_score"] is None):
            raise ValueError("Required performance fields missing or invalid")
        profile_row, season_row = profiles.get(key[0]), seasons.get(key[1])
        if profile_row is None or season_row is None:
            raise ValueError("Missing player/season join")
        profile = retain("player_profiles", profile_row)
        season = retain("seasons", season_row)
        group = "goalie" if definition.kind == "goalie" else ("defense" if profile.position == "D" else "forward")
        if profile.position is None or (profile.position == "G") != (definition.kind == "goalie") or season.salary_cap is None:
            raise ValueError("Required position or salary-cap context missing")
        performance = metrics["game_score"] if definition.kind == "skater" else (
            metrics["expected_goals_against"] - metrics["goals_against"] if metrics["goals_against"] is not None else None)
        if performance is None:
            raise ValueError("Required goalie performance field missing")
        birth = profile.birth_date
        as_of = date(key[1], 10, 1)
        age = as_of.year - birth.year - ((as_of.month, as_of.day) < (birth.month, birth.day)) if birth else None
        player_seasons[key] = {"player_id": key[0], "season": key[1], "position_group": group,
            "age": age, "salary_cap_cents": season.salary_cap, **traditional, **metrics,
            "performance_per_60": performance * 3600 / metrics["ice_time"],
            "toi_per_game": metrics["ice_time"] / traditional["games_played"]}
    if not player_seasons:
        raise ValueError("No eligible player-season rows")
    if set(player_seasons) != set(definition.expected_player_seasons):
        raise ValueError("Eligible player-seasons differ from the independently audited expected population")
    # The existing skater definition: median performance of the bottom 20% by
    # TOI/game, separately within each season and position group.
    from statistics import median
    groups = {}
    for row in player_seasons.values():
        groups.setdefault((row["season"], row["position_group"]), []).append(row)
    for rows in groups.values():
        ordered = sorted(row["toi_per_game"] for row in rows)
        index = (len(ordered) - 1) * 0.2
        lower = int(index)
        threshold = ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (index - lower)
        baseline = median(row["performance_per_60"] for row in rows if row["toi_per_game"] <= threshold)
        for row in rows:
            row["performance_above_replacement"] = row["performance_per_60"] - baseline
    rows = []
    for key, row in sorted(player_seasons.items()):
        if key[1] > last_season:
            continue
        target = player_seasons.get((key[0], key[1] + 1))
        # Split by target season so no training label crosses into validation.
        split = "train" if key[1] + 1 <= definition.train_through else "validation" if key[1] + 1 == definition.validation_season else "test" if key[1] + 1 == definition.test_season else "inference"
        label = target["performance_above_replacement"] * target["ice_time"] / 3600 if target else None
        rows.append({**row, "split": split, "target_season": key[1] + 1,
                     "target_hockey_value": label, "training_label_available": label is not None})
    observed_splits = {row["split"] for row in rows if row["target_hockey_value"] is not None}
    if not rows or not {"train", "validation", "test"} <= observed_splits:
        raise ValueError("Every declared time split requires observed eligible targets")
    for row in rows:
        if any(isinstance(value, float) and not isfinite(value) for value in row.values()):
            raise ValueError("Nonfinite dataset value")
    missing = {field: sum(row[field] is None for row in rows) for field in rows[0]}
    quality = {"passed": True, "duplicate_player_seasons": 0, "population_matches_audit": True, "missingness": missing,
               "rows_by_split": {split: sum(row["split"] == split for row in rows) for split in ("train", "validation", "test", "inference")},
               "unobserved_targets": sum(row["target_hockey_value"] is None for row in rows)}
    pins = tuple(InputRevision(dataset=dataset, record_key=tuple(RECORD_DEFINITIONS[dataset].json_key(stored.write.decoded())),
        revision=stored.revision, content_digest=stored.write.content_digest) for dataset, stored in sorted(used.values(), key=lambda item: (item[0], item[1].write.payload, item[1].revision)))
    definitions = {"performance": "game_score" if definition.kind == "skater" else "expected_goals_against - goals_against",
        "target": "next season performance above replacement per 60 * next season TOI hours",
        "replacement": "season/position median in bottom 20 percent by TOI/game; min_games eligibility",
        "contract_features": "excluded", "splits": definition.model_dump(mode="json"),
        "temporal_support": "retrospective accepted snapshot; historical prediction-date availability unsupported"}
    payload = canonical_json({"schema_version": "1", "transformation": TRANSFORMATION,
                              "definition": definition.model_dump(mode="json"), "rows": rows})
    digest = sha256(payload).hexdigest()
    version = sha256(canonical_json({"content": digest, "inputs": [pin.model_dump(mode="json") for pin in pins],
        "cutoff": cutoff.isoformat(), "first": first_season, "last": last_season})).hexdigest()
    manifest = DatasetVersion(dataset_id=definition.dataset_id, version=version, input_revisions=pins,
        cutoff=cutoff, row_count=len(rows), quality_results=quality, schema_version="1",
        transformation_version=TRANSFORMATION, feature_definitions=definitions,
        scope={"first_season": first_season, "last_season": last_season, "game_type": 2,
               "artifact_key": digest, "artifact_format": "canonical-json", "retention": "indefinite while published"},
        content_digest=digest, point_in_time_supported=False)
    return BuiltDataset(manifest, payload)


def dataset_operation(definitions, artifacts, *, cutoff=None):
    definitions = tuple(definitions)
    if len({definition.dataset_id for definition in definitions}) != len(definitions):
        raise ValueError("Dataset definitions require distinct IDs")

    def collect(ctx, cursor):
        snapshot = ctx.reader.snapshot(ctx.config.environment, accepted_before=cutoff or ctx.run.started_at)
        inputs = read_inputs(ctx.reader, snapshot)
        items = []
        for definition in definitions:
            built = build_dataset(definition, inputs, cutoff=snapshot.accepted_before,
                first_season=ctx.config.first_season, last_season=ctx.config.last_season)
            if ctx.config.mode != "validation":
                if artifacts.put(built.payload) != built.manifest.content_digest:
                    raise ValueError("Artifact storage digest differs")
            items.append(source_record(ctx, "datasets", built.manifest, source="dataset-builder",
                key=f"{built.manifest.dataset_id}/{built.manifest.version}", version=TRANSFORMATION))
        yield from batches(ctx, items, cursor, partition="datasets")

    return JobOperation(collect, ready=lambda ctx: bool(definitions) and not any(
        dataset in INPUTS for dataset, key in ctx.overlay))


def reproduce_dataset(reader, environment, manifest, artifacts):
    """Rebuild solely from retained exact revisions and verify published bytes."""
    snapshot = reader.snapshot(environment, accepted_before=manifest.cutoff)
    inputs = {dataset: [] for dataset in INPUTS}
    for pin in manifest.input_revisions:
        if pin.dataset not in inputs:
            raise ValueError("Unsupported published dataset input")
        stored = reader.get(pin.dataset, pin.record_key, snapshot=snapshot, revision=pin.revision)
        if stored is None or stored.write.content_digest != pin.content_digest:
            raise ValueError("Published input revision is absent or differs")
        inputs[pin.dataset].append(stored)
    definition = DatasetDefinition.model_validate_json(canonical_json(manifest.feature_definitions["splits"]))
    built = build_dataset(definition, inputs, cutoff=manifest.cutoff,
        first_season=manifest.scope["first_season"], last_season=manifest.scope["last_season"])
    if built.manifest != manifest or built.payload != artifacts.read(manifest.content_digest):
        raise ValueError("Published dataset is not reproducible")
    return built

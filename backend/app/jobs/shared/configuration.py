"""Explicit execution scope; no environment variables or database connections."""
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import get_args

from pydantic import Field, StrictBool, model_validator

from .data_contracts import Count, Environment, Mode, Record, Season, Text, canonical_json


@dataclass(frozen=True)
class JobSpec:
    outputs: tuple[str, ...]
    inputs: tuple[str, ...] = ()
    history_start: int = 2008
    current_only: bool = False
    optional_reads: tuple[str, ...] = ()
    supporting_outputs: tuple[str, ...] = ()

    @property
    def accepted_outputs(self):
        return self.outputs + self.supporting_outputs


JOBS = MappingProxyType({
    "teams_seasons": JobSpec(("franchises", "teams", "seasons", "team_seasons")),
    "player_profiles": JobSpec(("player_profiles",), optional_reads=("teams", "team_seasons", "games", "source_observations")),
    "team_rosters": JobSpec(("memberships", "roster_observations"), ("teams", "seasons", "player_profiles"), optional_reads=("team_seasons",)),
    "source_id_mappings": JobSpec(("source_mappings",), ("teams", "player_profiles")),
    "contracts": JobSpec(("contracts", "contract_seasons"), ("player_profiles", "seasons", "source_mappings"), optional_reads=("teams", "team_seasons", "basic_stats", "memberships", "refresh_requests", "refresh_completions"), supporting_outputs=("seasons", "refresh_completions")),
    "basic_stats": JobSpec(("basic_stats",), ("player_profiles", "teams", "seasons"), optional_reads=("team_seasons",)),
    "transactions": JobSpec(("transactions", "refresh_requests"), ("player_profiles", "teams", "source_mappings"), current_only=True),
    "roster_reconciliation": JobSpec(("roster_state",), ("memberships", "transactions"), current_only=True,
        optional_reads=("roster_observations", "roster_overrides", "player_profiles", "teams", "source_observations")),
    "game_schedule": JobSpec(("games",), ("teams", "seasons"), optional_reads=("team_seasons",)),
    "game_details": JobSpec(("game_stats", "game_events"), ("games", "player_profiles"), optional_reads=("teams", "game_stats", "game_events", "pipeline_runs")),
    "moneypuck_stats": JobSpec(("moneypuck_skater_stats", "moneypuck_goalie_stats", "moneypuck_team_stats", "moneypuck_line_stats"), ("teams", "seasons", "player_profiles", "source_mappings"), optional_reads=("team_seasons",)),
    "moneypuck_shots": JobSpec(("shots",), ("games", "player_profiles", "source_mappings"), optional_reads=("teams", "team_seasons", "shots")),
    "edge": JobSpec(("edge_summaries", "edge_games", "edge_events"), ("teams", "seasons", "player_profiles"), history_start=2021, optional_reads=("games", "team_seasons", "basic_stats", "memberships")),
    "datasets": JobSpec(("datasets",), ("basic_stats", "player_profiles", "seasons", "moneypuck_skater_stats", "moneypuck_goalie_stats")),
})


def execution_mode(selected, mode, *, validation_only=False):
    """Check the requested operation before applying validation-only execution."""
    if mode not in get_args(Mode):
        raise ValueError("Unsupported execution mode")
    if mode == "backfill" and any(JOBS[job].current_only for job in selected):
        raise ValueError("Current-only jobs cannot be backfilled, including validation-only execution")
    return "validation" if validation_only else mode


class JobConfig(Record):
    job: Text
    environment: Environment
    mode: Mode
    current_season: Season
    first_season: Season
    last_season: Season
    game_types: tuple[int, ...] = (2, 3)
    enabled: StrictBool = True
    resume: StrictBool = False
    # Adapter supplies this identity. Never infer the target from ambient ENV.
    target_environment: Environment
    max_batches: Count = Field(default=10000, gt=0, le=100000)
    max_batch_records: Count = Field(default=1000, gt=0, le=10000)
    correction_lookback_days: Count = 0
    max_input_age_seconds: Count = 0

    @model_validator(mode="after")
    def execution_scope(self):
        if self.job not in JOBS:
            raise ValueError("Unknown job")
        execution_mode((self.job,), self.mode)
        spec = JOBS[self.job]
        if self.environment != self.target_environment:
            raise ValueError("Execution and adapter environments differ")
        if not spec.history_start <= self.first_season <= self.last_season <= self.current_season:
            raise ValueError("Unsupported season range")
        if not self.game_types or len(set(self.game_types)) != len(self.game_types) or any(type(t) is not int or t not in (2, 3) for t in self.game_types):
            raise ValueError("Only distinct regular-season/playoff game types are supported")
        if spec.current_only and (self.first_season != self.current_season or self.last_season != self.current_season):
            raise ValueError("Current-only jobs do not support historical loads")
        if self.resume and self.mode not in ("initial", "backfill"):
            raise ValueError("Resume is supported only for initial loads and backfills")
        return self

    @property
    def scope(self):
        return {"first_season": self.first_season, "last_season": self.last_season,
                "game_types": sorted(self.game_types), "correction_lookback_days": self.correction_lookback_days,
                **({"max_input_age_seconds":self.max_input_age_seconds} if self.max_input_age_seconds else {})}

    @property
    def scope_key(self):
        # Initial/backfill progress is independent of refresh progress.
        return sha256(canonical_json({"mode": self.mode, **self.scope})).hexdigest()

    @property
    def conflict_scopes(self):
        return tuple(sorted(set(self.write_scopes) | set(self.read_scopes)))

    @property
    def write_scopes(self):
        return tuple(sorted(f"dataset:{name}" for name in JOBS[self.job].accepted_outputs))

    @property
    def read_scopes(self):
        spec = JOBS[self.job]
        freshness = ("pipeline_runs",) if self.max_input_age_seconds else ()
        return tuple(sorted({f"dataset:{name}" for name in (*spec.inputs, *spec.optional_reads, *freshness)} - set(self.write_scopes)))


def ordered_jobs(selected, *, catalog=JOBS):
    """Order only the requested operations by their declared dataset dependencies.

    Dependencies outside the selection remain prerequisites of the supplied
    database. Catalog order only breaks ties between independent operations.
    """
    selected = tuple(selected)
    if not selected or len(set(selected)) != len(selected) or any(job not in catalog for job in selected):
        raise ValueError("Select distinct known setup jobs")
    producers = {}
    for job, spec in catalog.items():
        for dataset in spec.outputs:
            if dataset in producers:
                raise ValueError(f"Multiple producers declared for {dataset}")
            producers[dataset] = job
    dependencies = {job: {producers[dataset] for dataset in catalog[job].inputs
                         if dataset in producers and producers[dataset] in selected}
                    for job in selected}
    remaining, result = set(selected), []
    while remaining:
        ready = [job for job in catalog if job in remaining and not dependencies[job] & remaining]
        if not ready:
            raise ValueError("Job dependency cycle")
        result.extend(ready)
        remaining.difference_update(ready)
    return tuple(result)

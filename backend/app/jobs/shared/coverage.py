"""Versioned data coverage requirements for the replacement pipelines.

This module has no database or network dependencies. It checks coverage evidence,
not record types, source truth, freshness, or persistence. Those checks belong to
the source/data contracts and execution foundation.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping


POLICY_VERSION = "3"
GAME_TYPES = (2, 3)


@dataclass(frozen=True)
class DatasetPolicy:
    source: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    required: bool = True
    history_start: int | None = None
    game_types: tuple[int, ...] = ()
    current_only: bool = False
    allows_future_seasons: bool = False


# Logical field names are independent of source spelling and database columns.
# Types, units, and relationships are defined separately in data_contracts.py.
DATASET_POLICIES: Mapping[str, DatasetPolicy] = MappingProxyType(
    {
        "teams": DatasetPolicy(
            source="NHL",
            required_fields=("team_id", "name", "abbreviation",),
            optional_fields=("city", "franchise_id",),
        ),
        "seasons": DatasetPolicy(
            source="NHL",
            required_fields=("season",),
            optional_fields=("salary_cap",),
            history_start=2008,
        ),
        "player_profiles": DatasetPolicy(
            source="NHL",
            required_fields=("player_id", "first_name", "last_name",),
            optional_fields=("birth_date", "position", "nationality", "shoots_catches",),
        ),
        "memberships": DatasetPolicy(
            source="NHL",
            required_fields=("player_id", "team_id", "season",),
            optional_fields=("effective_from", "effective_to",),
            history_start=2008,
        ),
        "source_mappings": DatasetPolicy(
            source="accepted sources",
            required_fields=("source", "source_id", "entity_type", "canonical_id",),
        ),
        "contracts": DatasetPolicy(
            source="Cap Space",
            required_fields=("contract_id", "player_id", "start_season", "end_season",),
            optional_fields=(
                "signed_on",
                "signing_team_id",
                "contract_type",
                "clauses",
                "total_value",
            ),
        ),
        "contract_seasons": DatasetPolicy(
            source="Cap Space",
            required_fields=("contract_id", "player_id", "season", "cap_hit",),
            optional_fields=(
                "base_salary",
                "signing_bonus",
                "performance_bonus",
                "total_cash",
                "owning_team_id",
            ),
            history_start=2008,
            allows_future_seasons=True,
        ),
        "basic_stats": DatasetPolicy(
            source="Cap Space",
            required_fields=("player_id", "season", "game_type", "team_scope", "games_played",),
            optional_fields=(
                "goals",
                "assists",
                "points",
                "time_on_ice",
                "wins",
                "saves",
                "shots_against",
            ),
            history_start=2008,
            game_types=GAME_TYPES,
        ),
        "transactions": DatasetPolicy(
            source="USA Today",
            required_fields=("source_id", "event_date", "event_type", "participants",),
            optional_fields=("description", "from_team_id", "to_team_id",),
            current_only=True,
        ),
        "roster_state": DatasetPolicy(
            source="NHL and accepted transactions",
            required_fields=("player_id", "status", "evidence",),
            optional_fields=("team_id", "effective_date",),
            current_only=True,
        ),
        "games": DatasetPolicy(
            source="NHL",
            required_fields=(
                "game_id",
                "season",
                "game_type",
                "home_team_id",
                "away_team_id",
                "start_time",
                "status",
            ),
            optional_fields=("home_score", "away_score",),
            history_start=2008,
            game_types=GAME_TYPES,
        ),
        "game_stats": DatasetPolicy(
            source="NHL",
            required_fields=("game_id", "team_id", "entity_id", "entity_type",),
            optional_fields=("goals", "assists", "shots", "time_on_ice", "saves",),
            history_start=2008,
            game_types=GAME_TYPES,
        ),
        "game_events": DatasetPolicy(
            source="NHL",
            required_fields=("game_id", "event_id", "event_type", "period", "time_in_period",),
            optional_fields=("player_id", "team_id", "x", "y",),
            history_start=2008,
            game_types=GAME_TYPES,
        ),
        "moneypuck_skater_stats": DatasetPolicy(
            source="MoneyPuck",
            required_fields=(
                "player_id",
                "season",
                "game_type",
                "team_scope",
                "situation",
                "ice_time",
                "expected_goals",
            ),
            optional_fields=("on_ice_expected_goals",),
            history_start=2008,
            game_types=GAME_TYPES,
        ),
        "moneypuck_goalie_stats": DatasetPolicy(
            source="MoneyPuck",
            required_fields=(
                "player_id",
                "season",
                "game_type",
                "team_scope",
                "situation",
                "ice_time",
                "expected_goals_against",
            ),
            optional_fields=("goals_against",),
            history_start=2008,
            game_types=GAME_TYPES,
        ),
        "moneypuck_team_stats": DatasetPolicy(
            source="MoneyPuck",
            required_fields=(
                "team_id",
                "season",
                "game_type",
                "situation",
                "ice_time",
                "expected_goals_for",
                "expected_goals_against",
            ),
            history_start=2008,
            game_types=GAME_TYPES,
        ),
        "moneypuck_line_stats": DatasetPolicy(
            source="MoneyPuck",
            required_fields=(
                "player_ids",
                "team_id",
                "season",
                "game_type",
                "situation",
                "ice_time",
                "expected_goals_for",
                "expected_goals_against",
            ),
            history_start=2008,
            game_types=GAME_TYPES,
        ),
        "shots": DatasetPolicy(
            source="MoneyPuck",
            required_fields=("shot_id", "game_id", "season", "game_type", "outcome",),
            optional_fields=("player_id", "team_id", "x", "y", "expected_goals",),
            history_start=2008,
            game_types=GAME_TYPES,
        ),
        "edge_summaries": DatasetPolicy(
            source="NHL EDGE",
            required_fields=(
                "entity_id",
                "entity_type",
                "season",
                "game_type",
                "metrics",
                "observed_at",
            ),
            optional_fields=("breakdowns",),
            history_start=2021,
            game_types=GAME_TYPES,
        ),
        "edge_games": DatasetPolicy(
            source="NHL EDGE",
            required_fields=("game_id", "entity_id", "metrics", "observed_at",),
            required=False,
            history_start=2021,
            game_types=GAME_TYPES,
        ),
        "edge_events": DatasetPolicy(
            source="NHL EDGE",
            required_fields=("event_id", "entity_id", "metrics", "observed_at",),
            required=False,
            history_start=2021,
            game_types=GAME_TYPES,
        ),
        "datasets": DatasetPolicy(
            source="validated inputs",
            required_fields=(
                "dataset_id",
                "version",
                "input_revisions",
                "cutoff",
                "row_count",
                "quality_results",
            ),
        ),
    }
)


@dataclass(frozen=True)
class RecordCoverage:
    missing_required: tuple[str, ...]
    missing_optional: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.missing_required


def check_record_coverage(dataset: str, record: Mapping[str, object]) -> RecordCoverage:
    """Check field availability without changing values or substituting zeros."""
    policy = DATASET_POLICIES[dataset]

    def missing(field: str) -> bool:
        value = record.get(field)
        return (
            value is None
            or (isinstance(value, str) and not value.strip())
            or (isinstance(value, (list, tuple, dict, set, frozenset)) and not value)
        )

    return RecordCoverage(
        tuple(field for field in policy.required_fields if missing(field)),
        tuple(field for field in policy.optional_fields if missing(field)),
    )


@dataclass(frozen=True)
class CoveragePartition:
    dataset: str
    season: int | None = None
    game_type: int | None = None


@dataclass(frozen=True)
class CoverageObservation:
    partition: CoveragePartition
    expected_records: int | None
    accepted_records: int
    collection_complete: bool
    invalid_records: int = 0
    unresolved_records: int = 0
    missing_required_fields: tuple[str, ...] = ()
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        counts = (self.accepted_records, self.invalid_records, self.unresolved_records)
        if self.expected_records is not None:
            counts += (self.expected_records,)
        if any(type(count) is not int or count < 0 for count in counts):
            raise ValueError("Record counts must be nonnegative integers")
        if type(self.collection_complete) is not bool:
            raise ValueError("collection_complete must be a boolean")
        if self.expected_records is not None and self.accepted_records > self.expected_records:
            raise ValueError("Accepted records exceed the expected population")


@dataclass(frozen=True)
class CoverageIssue:
    partition: CoveragePartition
    code: str
    blocking: bool
    message: str


@dataclass(frozen=True)
class CoverageReport:
    policy_version: str
    requested: tuple[CoveragePartition, ...]
    issues: tuple[CoverageIssue, ...]

    @property
    def complete(self) -> bool:
        """Completion applies only to the explicitly requested partitions."""
        return not any(issue.blocking for issue in self.issues)


def _validate_partition(partition: CoveragePartition, current_season: int, mode: str) -> None:
    policy = DATASET_POLICIES[partition.dataset]
    if policy.current_only and mode == "backfill":
        raise ValueError(f"{partition.dataset} does not support historical backfills")
    if policy.history_start is None:
        if partition.season is not None:
            raise ValueError(f"{partition.dataset} is not partitioned by season")
    elif type(partition.season) is not int or partition.season < policy.history_start:
        raise ValueError(f"{partition.dataset} requires a season starting at {policy.history_start}")
    elif partition.season > current_season and not policy.allows_future_seasons:
        raise ValueError(f"{partition.dataset} cannot request an unpublished future season")
    if policy.game_types:
        if type(partition.game_type) is not int or partition.game_type not in policy.game_types:
            raise ValueError("Only regular season (2) and playoffs (3) are supported")
    elif partition.game_type is not None:
        raise ValueError(f"{partition.dataset} is not partitioned by game type")


def assess_coverage(
    requested: Iterable[CoveragePartition],
    observations: Iterable[CoverageObservation],
    *,
    current_season: int,
    mode: str = "initial",
) -> CoverageReport:
    """Assess accepted coverage against an explicit, independently derived scope.

    Expected counts must come from a source manifest or reference population,
    never from the number of rows that happened to load. Counts supplement
    adapter checks of identities, duplicates, and relationships; they cannot
    establish those properties. Unknown counts and incomplete enumeration do
    not prove completion, even when a request succeeds.
    """
    if type(current_season) is not int or current_season < 2008:
        raise ValueError("current_season must be a starting year of at least 2008")
    if mode not in ("initial", "refresh", "backfill"):
        raise ValueError("Unsupported execution mode")
    partitions = tuple(requested)
    if not partitions or len(set(partitions)) != len(partitions):
        raise ValueError("Request at least one unique coverage partition")
    for partition in partitions:
        _validate_partition(partition, current_season, mode)

    observed: dict[CoveragePartition, CoverageObservation] = {}
    for observation in observations:
        if observation.partition not in partitions or observation.partition in observed:
            raise ValueError("Observations must belong to the request and occur once per partition")
        observed[observation.partition] = observation

    issues: list[CoverageIssue] = []
    for partition in partitions:
        policy = DATASET_POLICIES[partition.dataset]

        def issue(code: str, message: str) -> None:
            issues.append(CoverageIssue(partition, code, policy.required, message))

        observation = observed.get(partition)
        if observation is None:
            issue("NOT_PROCESSED", "No coverage evidence was supplied")
            continue
        if observation.unavailable_reason is not None:
            issue("UNAVAILABLE", observation.unavailable_reason)
        if not observation.collection_complete:
            issue("INCOMPLETE_COLLECTION", "The requested source range was not fully enumerated")
        if observation.expected_records is None:
            issue("UNKNOWN_EXPECTED_COUNT", "The expected population has not been established")
        elif observation.accepted_records < observation.expected_records:
            issue(
                "MISSING_RECORDS",
                f"Accepted {observation.accepted_records} of "
                f"{observation.expected_records} expected records",
            )
        if observation.invalid_records:
            issue("INVALID_RECORDS", f"{observation.invalid_records} records failed validation")
        if observation.unresolved_records:
            issue("UNRESOLVED_IDENTITIES", f"{observation.unresolved_records} records have unresolved identities")
        if observation.missing_required_fields:
            issue("MISSING_REQUIRED_FIELDS", ", ".join(observation.missing_required_fields))
    return CoverageReport(POLICY_VERSION, partitions, tuple(issues))

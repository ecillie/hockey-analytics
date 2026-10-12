"""Shared acceptance boundary. Incomplete/invalid batches cannot advance progress."""
from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from .configuration import JOBS
from .data_contracts import RECORD_DEFINITIONS, Record, SourceObservation, ValidationIssue, validate_batch, validate_record
from .identity import UnresolvedIdentity


@dataclass(frozen=True)
class SourceRecord:
    dataset: str
    payload: object
    observation: SourceObservation


@dataclass(frozen=True)
class CollectionBatch:
    records: tuple[SourceRecord, ...]
    cursor: object
    expected_records: int | None
    collection_complete: bool = True
    final: bool = False

    def validate_limits(self, max_records):
        if (not isinstance(self.records, tuple) or len(self.records) > max_records
                or any(not isinstance(item, SourceRecord) for item in self.records)
                or type(self.collection_complete) is not bool or type(self.final) is not bool):
            raise ValueError("Invalid/oversized collection batch")


@dataclass(frozen=True)
class ValidatedBatch:
    records: tuple[tuple[str, Record], ...]
    observations: tuple[SourceObservation, ...]
    issues: tuple[ValidationIssue, ...]
    unresolved: int = 0

    @property
    def observation_records(self):
        return tuple(("source_observations", observation) for observation in self.observations)

    @property
    def review_records(self):
        return self.observation_records + tuple(("validation_issues", issue) for issue in self.issues)


def validate_collection(batch, context, normalize: Callable):
    records, observations, issues = [], {}, []
    unresolved = 0

    def issue(dataset, message, observation_id=None, code="INVALID_RECORD"):
        issues.append(ValidationIssue(issue_id=uuid4(), run_id=context.run.run_id,
                      dataset=dataset, observation_id=observation_id, severity="error",
                      code=code, message=message, disposition="held"))

    if not batch.collection_complete or type(batch.expected_records) is not int or batch.expected_records != len(batch.records):
        issue(JOBS[context.config.job].outputs[0], "Missing or inconsistent independent batch enumeration", code="INCOMPLETE_COLLECTION")
    for item in batch.records:
        observation_id = None
        dataset = item.dataset if item.dataset in JOBS[context.config.job].outputs else JOBS[context.config.job].outputs[0]
        try:
            if item.dataset not in JOBS[context.config.job].outputs:
                raise ValueError("Record is outside the job's declared outputs")
            if not isinstance(item.observation, SourceObservation):
                raise ValueError("Record requires a source observation")
            observation = validate_record("source_observations", item.observation.model_dump())
            if observation.dataset != item.dataset:
                raise ValueError("Provenance dataset differs from record")
            old = observations.get(observation.observation_id)
            if old is not None and old != observation:
                raise ValueError("Conflicting observation identity")
            observations[observation.observation_id] = observation
            observation_id = observation.observation_id
            payload = normalize(item, context)
            record = validate_record(item.dataset, payload.model_dump() if isinstance(payload, Record) else payload)
            season = getattr(record, "season", None)
            if season is not None:
                # Future contract terms/references are retained, but never unrelated past seasons.
                permits_future = item.dataset in ("contract_seasons", "seasons")
                if season < context.config.first_season or (season > context.config.last_season and not permits_future):
                    raise ValueError("Record is outside requested seasons")
            if hasattr(record, "game_type") and record.game_type not in context.config.game_types:
                raise ValueError("Record is outside requested game types")
            definition = RECORD_DEFINITIONS[item.dataset]
            for fields in definition.unique_keys:
                values = tuple(getattr(record, field) for field in fields)
                if None not in values:
                    existing = context.find_unique(item.dataset, fields, values)
                    if existing is not None and definition.key(existing) != definition.key(record):
                        raise ValueError("Source identity already belongs to another canonical record")
            records.append((item.dataset, record))
        except UnresolvedIdentity as exc:
            unresolved += 1
            issue(dataset, str(exc), observation_id, "UNRESOLVED_IDENTITY")
        except (ValueError, TypeError, KeyError) as exc:
            issue(dataset, str(exc), observation_id)
    if not issues:
        try:
            validate_batch(tuple(records) + tuple(("source_observations", obs) for obs in observations.values()), context.lookup)
        except (ValueError, TypeError, KeyError) as exc:
            issue(JOBS[context.config.job].outputs[0], str(exc), code="INVALID_BATCH")
    return ValidatedBatch(tuple(records), tuple(observations.values()), tuple(issues), unresolved)

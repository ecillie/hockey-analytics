"""Offline Phase 2 fixture runtime. No network, durable persistence, or credentials."""
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4

from app.jobs.shared.configuration import JobConfig
from app.jobs.shared.data_contracts import SourceObservation, canonical_json
from app.jobs.shared.execution import Executor, JobOperation
from app.jobs.shared.validation import CollectionBatch, SourceRecord
from .contract_store import ContractStore

NOW = datetime(2026, 10, 12, 18, tzinfo=timezone.utc)
TEAM = {"team_id": 10, "name": "Fixture Team", "abbreviation": "FIX", "active": True}
SEASON = {"season": 2026, "end_year": 2027, "label": "2026-27"}
PLAYER = {"player_id": 7, "first_name": "Fixture", "last_name": "Player", "active": True}
MEMBERSHIP = {"membership_id": 1, "player_id": 7, "team_id": 10, "season": 2026}


def config(job="teams_seasons", **changes):
    return JobConfig(**{"job": job, "environment": "dev", "target_environment": "dev",
        "mode": "initial", "current_season": 2026, "first_season": 2026, "last_season": 2026, **changes})


def source(dataset, payload):
    observation = SourceObservation(observation_id=uuid4(), source="fixture", source_key=str(uuid4()),
        dataset=dataset, observed_at=NOW, content_digest=sha256(canonical_json(payload)).hexdigest(),
        transformation_version="fixture-1", scope={"season": 2026}, payload=payload)
    return SourceRecord(dataset, payload, observation)


def batch(*items, cursor=1, final=True, **changes):
    return CollectionBatch(records=items, cursor=cursor, expected_records=len(items), final=final, **changes)


def fixture_operations():
    references = batch(source("teams", TEAM), source("seasons", SEASON))
    profile = batch(source("player_profiles", PLAYER))
    membership = batch(source("memberships", MEMBERSHIP))
    return {
        "teams_seasons": JobOperation(lambda ctx, cursor: [references]),
        "player_profiles": JobOperation(lambda ctx, cursor: [profile]),
        "team_rosters": JobOperation(lambda ctx, cursor: [membership], ready=lambda ctx: all(
            ctx.lookup(dataset, key) is not None for dataset, key in (("teams", (10,)), ("seasons", (2026,)), ("player_profiles", (7,))))),
    }


def executor(store=None, operations=None):
    store = store or ContractStore()
    store.now = NOW
    return Executor(store, fixture_operations() if operations is None else operations,
                    target_environment="dev", now=lambda: NOW, pause=lambda delay: None)


def latest(store, dataset, key):
    row = store.get(dataset, key, snapshot=store.snapshot("dev", accepted_before=NOW))
    return row.write.decoded() if row else None


def create_runtime(environment):
    if environment != "dev":
        raise ValueError("Offline fixture runtime supports dev only")
    return executor()

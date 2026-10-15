"""Explicit, additive transition of public identity IDs into the revision ledger."""
from datetime import datetime, timezone
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import text

from app.jobs.shared.access_contracts import AcceptedBatch, make_write
from app.jobs.shared.data_contracts import (
    CONTRACT_VERSION, PipelineRun, RunCounters, SourceObservation, RECORD_DEFINITIONS, canonical_json, validate_record,
)
from app.jobs.shared.coverage import POLICY_VERSION
from .store import PostgresStore


def require_identity_transition(store):
    """Do not let an empty replacement allocate IDs already used by the API."""
    with store.engine.connect() as connection:
        ambiguous = connection.execute(text("""SELECT ids.player_id FROM public.player_external_ids ids
            JOIN public.data_sources s ON s.id=ids.source_id WHERE s.code='nhl'
            GROUP BY ids.player_id HAVING COUNT(DISTINCT external_id)>1 LIMIT 1""")).first()
        if ambiguous:
            raise ValueError("Ambiguous legacy NHL identity requires review")
        missing_player = connection.execute(text("""SELECT 1 FROM public.players p
            LEFT JOIN (SELECT ids.player_id, ids.external_id FROM public.player_external_ids ids
                JOIN public.data_sources s ON s.id=ids.source_id WHERE s.code='nhl') nhl ON nhl.player_id=p.id
            WHERE NOT EXISTS (SELECT 1 FROM public.pipeline_current r WHERE r.dataset='player_profiles'
                AND (r.payload->>'player_id')::bigint=p.id
                AND (nhl.external_id IS NULL OR r.payload->>'nhl_player_id'=nhl.external_id)) LIMIT 1""")).first()
        if missing_player:
            raise ValueError("Existing public identities need explicit --bootstrap-identities before replacement jobs")
        for table, dataset, key, external in (("teams","teams","team_id","nhl_team_id"),):
            missing = connection.execute(text(f"""SELECT 1 FROM public.{table} old
                WHERE NOT EXISTS (SELECT 1 FROM public.pipeline_current r WHERE r.dataset=:dataset
                AND (r.payload->>:key)::bigint=old.id
                AND (r.payload->>:external)::bigint IS NOT DISTINCT FROM old.{external}) LIMIT 1"""),
                {"dataset":dataset, "key":key, "external":external}).first()
            if missing:
                raise ValueError("Existing public identities need explicit --bootstrap-identities before replacement jobs")


def bootstrap_identities(engine, environment):
    store = PostgresStore(engine, environment)
    now, run_id = datetime.now(timezone.utc), uuid4()
    records = []
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            for row in connection.execute(text("SELECT * FROM public.teams ORDER BY id")).mappings():
                records.append(("teams", validate_record("teams", {"team_id":row["id"], "nhl_team_id":row["nhl_team_id"],
                    "name":row["name"], "abbreviation":row["abbreviation"], "city":row["city"], "active":row["active"]})))
            for row in connection.execute(text("""SELECT p.*, (SELECT array_agg(ids.external_id)
                FROM public.player_external_ids ids JOIN public.data_sources s ON s.id=ids.source_id
                WHERE ids.player_id=p.id AND s.code='nhl') nhl_ids FROM public.players p ORDER BY p.id""")).mappings():
                nhl_ids = row["nhl_ids"] or []
                if len(set(nhl_ids)) > 1 or any(not item.isdecimal() or int(item)<=0 for item in nhl_ids):
                    raise ValueError("Ambiguous/invalid legacy NHL identity requires review")
                records.append(("player_profiles", validate_record("player_profiles", {"player_id":row["id"],
                    "nhl_player_id":int(nhl_ids[0]) if nhl_ids else None, "first_name":row["first_name"], "last_name":row["last_name"],
                    "birth_date":row["birth_date"], "position":row["primary_position"], "nationality":row["nationality"],
                    "shoots_catches":row["shoots_catches"], "active":row["active"]})))
    mappings = []
    for dataset, value in records:
        external = value.nhl_player_id if dataset == "player_profiles" else value.nhl_team_id
        identity = value.player_id if dataset == "player_profiles" else value.team_id
        if external is not None:
            mappings.append(("source_mappings", validate_record("source_mappings", {
                "source":"nhl", "entity_type":"player" if dataset == "player_profiles" else "team",
                "source_id":str(external), "canonical_id":identity})))
    scopes = ("dataset:teams", "dataset:player_profiles", "dataset:source_mappings")
    with store.writer_lease(environment, conflict_scopes=scopes):
        snapshot = store.snapshot(environment, accepted_before=datetime.now(timezone.utc))
        writes = []
        for dataset, value in (*records, *mappings):
            definition = RECORD_DEFINITIONS[dataset]
            previous = store.get(dataset, definition.key(value), snapshot=snapshot)
            if previous is not None:
                old = previous.write.decoded()
                field = "canonical_id" if dataset == "source_mappings" else "nhl_player_id" if dataset == "player_profiles" else "nhl_team_id"
                if getattr(old,field) != getattr(value,field):
                    raise ValueError("Existing canonical identity differs from its legacy mapping")
                continue  # Retain newer accepted profiles rather than copying old attributes back.
            raw = value.model_dump(mode="json")
            digest = sha256(canonical_json(raw)).hexdigest()
            observation = SourceObservation(observation_id=uuid5(NAMESPACE_URL, f"{store.target_id}/legacy/{dataset}/{digest}"),
                source="legacy-identity-bootstrap", source_key=canonical_json(definition.json_key(value)).decode(),
                dataset=dataset, observed_at=now, content_digest=digest, transformation_version="legacy-identities-1",
                scope={"target":store.target_id, "identity_only":True}, payload=raw)
            writes.extend((make_write("source_observations",observation,expected_revision=None),
                make_write(dataset,value,expected_revision=None,observation_ids=(observation.observation_id,))))
        run = PipelineRun(run_id=run_id, job="identity_bootstrap", environment=environment, mode="initial",
            scope={"identity_only":True}, status="succeeded" if writes else "no_change", started_at=now,
            finished_at=datetime.now(timezone.utc), counters=RunCounters(read=len(records)+len(mappings),accepted=len(writes)//2),
            contract_version=CONTRACT_VERSION,coverage_policy_version=POLICY_VERSION)
        writes.append(make_write("pipeline_runs",run,expected_revision=None))
        batch = AcceptedBatch(batch_id=uuid4(),run_id=run_id,environment=environment,conflict_scopes=scopes,writes=tuple(writes))
        with store.transaction(environment,conflict_scopes=scopes) as transaction:
            transaction.stage(batch)
            return transaction.commit()

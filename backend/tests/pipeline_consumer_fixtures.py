"""Translate the established API SQL fixture into logical accepted records."""
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import text

from app.jobs.shared.access_contracts import AcceptedBatch, make_write
from app.jobs.shared.data_contracts import RECORD_DEFINITIONS, SourceObservation, canonical_json, validate_record
from .test_data_contracts import record
from .test_postgres_integration import SEED_SQL


def populate(engine, store):
    items = [("pipeline_runs", record("pipeline_runs"))]
    run_id = items[0][1].run_id
    with engine.begin() as connection:
        connection.exec_driver_sql(SEED_SQL)

        def copy(table, dataset, aliases=None, extra=None, where=""):
            for row in connection.execute(text(f"SELECT * FROM public.{table} {where}")).mappings():
                value = {(aliases or {}).get(name, name): item for name, item in row.items()}
                value.update(extra(row) if callable(extra) else extra or {})
                payload = {name:item for name,item in value.items() if name in RECORD_DEFINITIONS[dataset].model.model_fields}
                items.append((dataset, validate_record(dataset, payload)))

        copy("teams", "teams", {"id":"team_id"})
        copy("seasons", "seasons", {"start_year":"season", "salary_cap_cents":"salary_cap"}, where="WHERE start_year>=2008")
        copy("players", "player_profiles", {"id":"player_id", "primary_position":"position"})
        copy("player_team_stints", "memberships", {"id":"membership_id", "season_start_year":"season", "joined_on":"effective_from", "departed_on":"effective_to"})
        observation = record("source_observations")
        items.append(("source_observations", observation))
        copy("players", "roster_state", {"id":"player_id", "roster_status":"status"}, {"evidence":(observation.observation_id,)})
        copy("contracts", "contracts", {"id":"contract_id", "total_value_cents":"total_value", "average_value_cents":"average_value"})
        owner = dict(connection.execute(text("SELECT id,player_id FROM public.contracts")).all())
        aliases = {"season_start_year":"season", **{field+"_cents":field for field in ("cap_hit","base_salary","signing_bonus","performance_bonus","total_cash")}}
        copy("contract_seasons", "contract_seasons", aliases, lambda row:{"player_id":owner[row["contract_id"]]})
        aliases = {"season_start_year":"season", "stat_scope":"team_scope", "time_on_ice_seconds":"time_on_ice"}
        copy("skater_season_stats", "basic_stats", aliases, {"source":"nhl", "stat_kind":"skater"})
        copy("goalie_season_stats", "basic_stats", aliases, {"source":"nhl", "stat_kind":"goalie"})
        aliases = {"season_start_year":"season", "stat_scope":"team_scope", "ice_time_seconds":"ice_time", "individual_expected_goals":"expected_goals"}
        copy("skater_advanced_season_stats", "moneypuck_skater_stats", aliases, {"source":"moneypuck"})
        copy("goalie_advanced_season_stats", "moneypuck_goalie_stats", aliases,
             lambda row:{"source":"moneypuck", "goals_against":int(row["goals_against"])})
    writes = tuple(make_write(dataset, value, expected_revision=None,
        observation_ids=() if dataset in ("pipeline_runs", "source_observations") else (observation.observation_id,)) for dataset,value in items)
    batch = AcceptedBatch(batch_id=uuid4(), run_id=run_id, environment="dev",
        conflict_scopes=tuple("dataset:"+dataset for dataset in RECORD_DEFINITIONS), writes=writes)
    with store.transaction("dev", conflict_scopes=batch.conflict_scopes) as transaction:
        transaction.stage(batch)
        transaction.commit()

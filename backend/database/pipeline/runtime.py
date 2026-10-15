"""Explicit infrastructure factory for the replacement CLI.

Imports do not connect, initialize schemas, bind environments, or fetch sources.
"""
from datetime import datetime
import json
import os
from pathlib import Path

from sqlalchemy import create_engine

from app.config import get_database_settings
from app.jobs.dataset_processing import DatasetDefinition, dataset_operation
from app.jobs.game_data_operations import source_operations
from app.jobs.shared.execution import Executor
from app.jobs.shared.data_contracts import canonical_json
from app.jobs.shared.source_requests import RequestPolicy, SourceClient
from .artifacts import LocalArtifacts
from .store import PostgresStore, initialize_target
from .identities import bootstrap_identities, require_identity_transition


def create_runtime(environment):
    settings = get_database_settings()
    if settings.environment.value != environment:
        raise ValueError("Explicit runtime environment differs from configured infrastructure")
    engine = create_engine(settings.database_url, pool_pre_ping=True, hide_parameters=True,
        pool_size=settings.pool_size, max_overflow=settings.max_overflow,
        pool_recycle=settings.pool_recycle_seconds,
        connect_args={"connect_timeout": settings.connect_timeout_seconds})
    store = PostgresStore(engine, environment)
    require_identity_transition(store)
    operations = source_operations()
    path = os.getenv("PIPELINE_DATASET_CONFIG")
    if path:
        config = json.loads(Path(path).read_text())
        definitions = [DatasetDefinition.model_validate_json(canonical_json(item)) for item in config["definitions"]]
        cutoff = datetime.fromisoformat(config["cutoff"].replace("Z", "+00:00"))
        if cutoff.tzinfo is None:
            raise ValueError("Dataset cutoff requires an explicit timezone")
        operations["datasets"] = dataset_operation(definitions, LocalArtifacts(config["artifact_root"]), cutoff=cutoff)
    policies = {source: RequestPolicy() for source in ("nhl", "capspace", "capwages", "usatoday", "moneypuck", "nhl-edge")}
    return Executor(store, operations, target_environment=environment, client=SourceClient(policies))


def main(argv=None):
    from app.jobs.shared.cli import configure_cli, SafeArgumentParser
    from app.observability import configure_logging, log_event
    import logging
    configure_cli()
    command = SafeArgumentParser(description="Bind a migrated replacement database to one environment")
    command.add_argument("--environment", required=True, choices=("dev", "nonprod", "prod"))
    command.add_argument("--bootstrap-identities", action="store_true")
    args = command.parse_args(argv)
    configure_logging(environment=args.environment)
    try:
        settings = get_database_settings()
        if settings.environment.value != args.environment:
            raise ValueError("Explicit environment differs from configured infrastructure")
        engine = create_engine(settings.database_url, hide_parameters=True)
        try:
            initialize_target(engine, args.environment)
            if args.bootstrap_identities:
                bootstrap_identities(engine, args.environment)
        finally:
            engine.dispose()
    except Exception as exc:
        log_event(logging.getLogger(__name__), "database.binding_failed", level=logging.ERROR, error=exc)
        return 2
    print(json.dumps({"environment": args.environment, "initialized": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

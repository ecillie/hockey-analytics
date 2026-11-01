"""Create the initial TradeValue schema.

Revision ID: 20260910_0001
Revises: None
"""

import hashlib
from pathlib import Path

from alembic import op
from app.database import open_database_cursor
from app.shared.migrations.policy import SchemaChecksumPolicy


revision = "20260910_0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_SHA256 = "b29d0567ee3a17cb95abe37b00de0cf3589e809fb65019f67bd1e6b74509d2b5"
SCHEMA_PATH = Path(__file__).parents[2].joinpath("database", "schema.sql")


def _schema_body() -> str:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    digest = hashlib.sha256(schema.encode()).hexdigest()
    if violation := SchemaChecksumPolicy(expected=SCHEMA_SHA256).find_violation(
        path=SCHEMA_PATH, actual=digest
    ):
        raise violation
    lines = schema.splitlines()
    return "\n".join(
        line for line in lines if line.strip() not in {"BEGIN;", "COMMIT;"}
    )


def _execute_script(sql: str) -> None:
    context = op.get_context()
    if context.as_sql:
        context.impl.static_output(sql.rstrip() + "\n")
        return
    with open_database_cursor(op.get_bind().connection) as cursor:
        cursor.execute(sql)


def upgrade() -> None:
    _execute_script(_schema_body())


def downgrade() -> None:
    _execute_script(
        """
DROP TABLE IF EXISTS
    predictions,
    model_versions,
    player_game_stats,
    goalie_advanced_season_stats,
    skater_advanced_season_stats,
    goalie_season_stats,
    skater_season_stats,
    source_records,
    ingestion_runs,
    games,
    contract_seasons,
    contracts,
    player_team_stints,
    ltir_overrides,
    player_external_ids,
    players,
    teams,
    seasons,
    data_sources
CASCADE;
DROP TYPE IF EXISTS roster_status;
"""
    )

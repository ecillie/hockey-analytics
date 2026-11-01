"""Controlled failure stages without copying arbitrary exception messages."""

from alembic.util import CommandError
from app.config import ConfigurationError


def classify_migration_failure(error: Exception) -> str:
    if isinstance(error, ConfigurationError):
        stages = {
            ("TradeValue migrations", "require PostgreSQL"): "postgresql_required",
            (
                "DATABASE_URL or TEST_DATABASE_URL",
                "is required",
            ): "database_url_required",
        }
        return stages.get((error.field, error.reason), "configuration")
    return "framework" if isinstance(error, CommandError) else "execution"

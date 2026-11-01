"""Resolve operational database configuration without loading dotenv files."""

import os
from collections.abc import Mapping

from app.config import ConfigurationError


def database_url(values: Mapping[str, str] | None = None) -> str:
    values = os.environ if values is None else values
    primary = values.get("DATABASE_URL")
    if primary is not None and primary != "":
        return primary
    fallback = values.get("TEST_DATABASE_URL")
    if fallback is not None and fallback != "":
        return fallback
    raise ConfigurationError(
        field="DATABASE_URL or TEST_DATABASE_URL", reason="is required"
    )


def migration_database_url() -> str:
    url = database_url()
    if not url.startswith(("postgresql://", "postgresql+psycopg2://")):
        raise ConfigurationError(
            field="TradeValue migrations", reason="require PostgreSQL"
        )
    return url

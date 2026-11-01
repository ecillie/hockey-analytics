"""Alembic environment for TradeValue's PostgreSQL schema."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from app.shared.cli import ExitCode
from app.shared.environment import migration_database_url as database_url


def configure_migration_context(connection=None, *, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=None,
        literal_binds=url is not None,
        dialect_opts={"paramstyle": "named"},
        transaction_per_migration=True,
        compare_type=True,
        compare_server_default=True,
    )


def run_migrations_offline() -> None:
    configure_migration_context(url=database_url())
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config = context.config
    settings = config.get_section(config.config_ini_section, {})
    settings["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(
        settings,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"options": "-c lock_timeout=10000 -c statement_timeout=120000"},
    )

    with connectable.connect() as connection:
        configure_migration_context(connection)
        with context.begin_transaction():
            context.run_migrations()


def main() -> int:
    config = context.config
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)
    if context.is_offline_mode():
        run_migrations_offline()
        return ExitCode.SUCCESS
    run_migrations_online()
    return ExitCode.SUCCESS


main()

"""Safe logging and resource ownership for Alembic's environment callback."""

from dataclasses import dataclass
from collections.abc import Collection, Mapping
import logging
import os

from alembic import context
from alembic.runtime.migration import MigrationContext, MigrationInfo
from alembic.util import CommandError
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection
from backend.database.migrations.domain import MigrationOptions
from backend.database.migrations.util import classify_migration_failure

from app.shared.cli import ExitCode
from app.shared.cleanup import complete_cleanup
from app.shared.environment import migration_database_url
from app.shared.observability.domain import (
    CommandOutcome,
    InvocationContext,
    read_logging_settings,
)
from app.shared.observability.errors import LoggingSettingsError
from app.shared.observability.services import (
    configure_logging,
    start_command,
    configure_command_exceptions,
    finish_command,
)


logger = logging.getLogger(__name__)


@dataclass(slots=True, kw_only=True, frozen=True)
class MigrationProgress:
    invocation: InvocationContext
    offline: bool

    def __call__(
        self,
        ctx: MigrationContext,
        step: MigrationInfo,
        heads: Collection[object],
        run_args: Mapping[str, object],
    ) -> None:
        stage = (
            "stamp" if step.is_stamp else "upgrade" if step.is_upgrade else "downgrade"
        )
        logger.debug(
            "Migration step processed",
            extra=self.invocation.fields
            | {
                "event": "migration.step_rendered"
                if self.offline
                else "migration.step_pending",
                "stage": stage,
                "revision": step.up_revision_id
                if step.up_revision_id is not None
                else "base",
            },
        )


def configure_migration_context(
    connection: Connection | None = None,
    *,
    url: str | None = None,
    progress: MigrationProgress | None = None,
) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=None,
        literal_binds=url is not None,
        dialect_opts={"paramstyle": "named"},
        transaction_per_migration=True,
        compare_type=True,
        compare_server_default=True,
        on_version_apply=progress,
    )


def run_migrations_offline(progress: MigrationProgress) -> None:
    configure_migration_context(url=migration_database_url(), progress=progress)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online(progress: MigrationProgress) -> None:
    config = context.config
    settings = config.get_section(config.config_ini_section, {})
    settings["sqlalchemy.url"] = migration_database_url()
    connectable = engine_from_config(
        settings,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"options": "-c lock_timeout=10000 -c statement_timeout=120000"},
    )
    primary: BaseException | None = None
    try:
        with connectable.connect() as connection:
            configure_migration_context(connection, progress=progress)
            with context.begin_transaction():
                context.run_migrations()
    except BaseException as error:
        primary = error
        raise
    finally:
        complete_cleanup((connectable.dispose,), primary)


def execute_migrations(
    options: MigrationOptions, invocation: InvocationContext
) -> None:
    progress = MigrationProgress(invocation=invocation, offline=options.offline)
    logger.debug(
        "Migration mode selected",
        extra=invocation.fields
        | {
            "event": "migration.mode_selected",
            "stage": "offline" if options.offline else "online",
        },
    )
    if options.offline:
        run_migrations_offline(progress)
        return
    run_migrations_online(progress)


def main() -> int:
    config = context.config
    options = MigrationOptions(
        offline=context.is_offline_mode(),
        command_line=config.cmd_opts is not None,
        raise_errors=getattr(config.cmd_opts, "raiseerr", False) is True,
    )
    try:
        settings = read_logging_settings(os.environ)
    except LoggingSettingsError as error:
        if not options.command_line:
            raise
        raise CommandError(str(error)) from error
    configure_logging(settings)
    invocation = start_command("alembic")
    if options.command_line:
        configure_command_exceptions(invocation)
    try:
        execute_migrations(options, invocation)
    except Exception as error:
        if not options.command_line:
            finish_command(invocation, CommandOutcome.FAILED)
            raise
        logger.exception(
            "Migration command failed",
            extra=invocation.fields
            | {"event": "command.failed", "stage": classify_migration_failure(error)},
        )
        finish_command(invocation, CommandOutcome.FAILED)
        return (
            ExitCode.FRAMEWORK_FAILURE
            if isinstance(error, CommandError) and not options.raise_errors
            else ExitCode.FAILURE
        )
    finish_command(invocation, CommandOutcome.COMPLETED)
    return ExitCode.SUCCESS

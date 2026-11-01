"""Alembic-owned bootstrap; success returns control to the framework."""

from app.shared.cli import ExitCode
from backend.database.migrations.services import main


if (exit_code := main()) != ExitCode.SUCCESS:
    raise SystemExit(exit_code)

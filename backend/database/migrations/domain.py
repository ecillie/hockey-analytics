"""Immutable Alembic invocation mode at the framework boundary."""

from dataclasses import dataclass


@dataclass(slots=True, kw_only=True, frozen=True)
class MigrationOptions:
    offline: bool
    command_line: bool
    raise_errors: bool

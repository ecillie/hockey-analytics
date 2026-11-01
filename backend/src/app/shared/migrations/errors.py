"""Typed failure for changes to the frozen initial schema."""

from pathlib import Path


class SchemaChecksumError(RuntimeError):
    def __init__(self, *, path: Path, expected: str, actual: str) -> None:
        super().__init__(
            "backend/database/schema.sql is the frozen initial-schema snapshot; "
            "create a new Alembic revision instead of editing it; "
            f"{path}: expected {expected}, got {actual}"
        )
        self.path = path
        self.expected = expected
        self.actual = actual

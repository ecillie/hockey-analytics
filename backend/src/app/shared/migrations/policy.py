"""Invariant protecting the frozen initial-schema checksum."""

from dataclasses import dataclass
from pathlib import Path

from app.shared.migrations.errors import SchemaChecksumError


@dataclass(slots=True, kw_only=True, frozen=True)
class SchemaChecksumPolicy:
    expected: str

    def find_violation(self, *, path: Path, actual: str) -> SchemaChecksumError | None:
        if actual == self.expected:
            return None
        return SchemaChecksumError(path=path, expected=self.expected, actual=actual)

"""Frozen source scenarios for repository syntax verification."""

from dataclasses import dataclass

from backend.database.verify_python_rules import Rule


@dataclass(slots=True, kw_only=True, frozen=True)
class SyntaxCase:
    source: str
    rules: tuple[Rule, ...]
    lines: tuple[int, ...]

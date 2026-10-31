"""Borrowed resource handles for single-read pipeline verification."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Self


@dataclass(slots=True, kw_only=True, frozen=True)
class PipelineResources:
    connection: object

    @property
    def engine(self) -> Self:
        return self

    @contextmanager
    def connect(self) -> Generator[object]:
        yield self.connection


@dataclass(slots=True, kw_only=True, frozen=True)
class ReadScenario:
    connection: object
    calls: list[tuple[str, object]] = field(default_factory=list)

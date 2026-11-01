"""Borrowed resource handles for single-read pipeline verification."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Self
import pandas as pd
from sklearn.pipeline import Pipeline


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


@dataclass(slots=True, kw_only=True, frozen=True)
class DatasetScenario:
    players: pd.DataFrame
    caps: pd.DataFrame


@dataclass(slots=True, kw_only=True, frozen=True)
class TrainedScenario:
    model: Pipeline
    repeated: Pipeline
    test: pd.DataFrame

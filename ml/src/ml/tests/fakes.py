"""Borrowed resource handles for single-read pipeline verification."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Literal, Self
import pandas as pd
from sklearn.pipeline import Pipeline
from ml.domain import Metric, MetricValues


@dataclass(slots=True, kw_only=True, frozen=True)
class MetricScenario:
    current: MetricValues
    baseline: MetricValues
    tolerances: MetricValues


@dataclass(slots=True, kw_only=True, frozen=True)
class MetricFailureScenario:
    inputs: MetricScenario
    error: type[Exception]
    metric: Metric = Metric.MAE


@dataclass(slots=True, kw_only=True, frozen=True)
class MetadataFailureScenario:
    payload: dict[str, object]
    error: type[Exception] = ValueError
    message: str | None = None


type TemporalFailureValue = int | tuple[int, ...] | tuple[str, ...]
type TemporalFailureField = Literal["columns", "seasons", "invalid_rows"]


@dataclass(slots=True, kw_only=True, frozen=True)
class TemporalFailureScenario:
    data: pd.DataFrame
    error: type[Exception]
    context_field: TemporalFailureField
    expected: TemporalFailureValue


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
class FrameReader:
    frames: DatasetScenario
    reads: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.reads)

    def read_players(self, min_games: int) -> pd.DataFrame:
        self.reads.append("players")
        return self.frames.players

    def read_salary_caps(self) -> pd.DataFrame:
        self.reads.append("caps")
        return self.frames.caps


@dataclass(slots=True, kw_only=True, frozen=True)
class TrainedScenario:
    model: Pipeline
    repeated: Pipeline
    test: pd.DataFrame

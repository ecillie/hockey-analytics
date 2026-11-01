"""Behavioral catalog, migration, and HTTP boundaries."""

from dataclasses import dataclass, field
from collections.abc import Iterator, Mapping
from typing import Literal, Self
import httpx
from io import StringIO
from pathlib import Path
from types import ModuleType


@dataclass(slots=True, kw_only=True, frozen=True)
class ScalarResult:
    values: tuple[object, ...]

    def scalars(self) -> Self:
        return self

    def all(self) -> list[object]:
        return list(self.values)

    def scalar_one(self) -> object:
        (value,) = self.values
        return value


@dataclass(slots=True, kw_only=True, frozen=True)
class CatalogDatabase:
    tables: tuple[str, ...] = ()
    versions: tuple[str, ...] = ()
    version_table_exists: bool = False
    sources: tuple[str, ...] = ("capspace", "capwages", "moneypuck", "nhl")
    seasons: int = 22
    statements: list[str] = field(default_factory=list)

    def execute(self, query: object) -> ScalarResult:
        statement = str(query)
        self.statements.append(statement)
        if "information_schema.tables" in statement:
            return ScalarResult(values=self.tables)
        if "to_regclass" in statement:
            return ScalarResult(values=(self.version_table_exists,))
        if "FROM alembic_version" in statement and self.version_table_exists:
            return ScalarResult(values=self.versions)
        if "FROM data_sources" in statement:
            return ScalarResult(values=self.sources)
        if "FROM seasons" in statement:
            return ScalarResult(values=(self.seasons,))
        raise AssertionError(f"unexpected catalog query: {statement}")


@dataclass(slots=True, kw_only=True, frozen=True)
class MigrationRevision:
    revision: str = "revision"
    doc: str = "description"
    is_merge_point: bool = False


@dataclass(slots=True, kw_only=True, frozen=True)
class MigrationHistory:
    revisions: tuple[MigrationRevision, ...]
    heads: tuple[str, ...] = ("head",)

    def get_heads(self) -> list[str]:
        return list(self.heads)

    def walk_revisions(self, *, base: str, head: str) -> Iterator[MigrationRevision]:
        return iter(self.revisions)


@dataclass(slots=True, kw_only=True, frozen=True)
class SavedApiClient:
    responses: Mapping[str, httpx.Response]
    paths: list[str] = field(default_factory=list)

    def get(self, path: str) -> httpx.Response:
        self.paths.append(path)
        return self.responses[path]


@dataclass(slots=True, kw_only=True, frozen=True)
class MigrationOutput:
    statements: list[str] = field(default_factory=list)

    def static_output(self, statement: str) -> None:
        self.statements.append(statement)


@dataclass(slots=True, kw_only=True, frozen=True)
class MigrationContext:
    as_sql: bool
    impl: MigrationOutput = field(default_factory=MigrationOutput)


@dataclass(slots=True, kw_only=True, frozen=True)
class MigrationCursor:
    statements: list[str] = field(default_factory=list)
    closures: list[bool] = field(default_factory=list)

    def execute(self, statement: str) -> None:
        self.statements.append(statement)

    def close(self) -> None:
        self.closures.append(True)


@dataclass(slots=True, kw_only=True, frozen=True)
class MigrationConnection:
    active_cursor: MigrationCursor

    def cursor(self) -> MigrationCursor:
        return self.active_cursor


@dataclass(slots=True, kw_only=True, frozen=True)
class MigrationBind:
    connection: MigrationConnection


type SmokeResponse = tuple[int, object, str]


@dataclass(slots=True, kw_only=True, frozen=True)
class ScriptedRequest:
    responses: tuple[SmokeResponse | OSError, ...]
    urls: list[str] = field(default_factory=list)

    def __call__(self, url: str, timeout: float) -> SmokeResponse:
        index = len(self.urls)
        self.urls.append(url)
        response = self.responses[index]
        if isinstance(response, OSError):
            raise response
        return response


@dataclass(slots=True, kw_only=True, frozen=True)
class DelayRecorder:
    delays: list[float] = field(default_factory=list)

    def __call__(self, delay: float) -> None:
        self.delays.append(delay)


@dataclass(slots=True, kw_only=True, frozen=True)
class ReadinessScenario:
    request: ScriptedRequest
    sleep: DelayRecorder


@dataclass(slots=True, kw_only=True, frozen=True)
class StageOutcome[R]:
    result: R
    failure: BaseException | None = None
    name: str = "stage"
    events: list[str] = field(default_factory=list)

    def __call__(self, *args: object, **kwargs: object) -> R:
        self.events.append(self.name)
        if self.failure is not None:
            raise self.failure
        return self.result


@dataclass(slots=True, kw_only=True, frozen=True)
class MigrationCleanupScenario:
    create: StageOutcome[None]
    drop: StageOutcome[None]
    primary: BaseException | None
    events: list[str]

    @property
    def expected_failure(self) -> BaseException | None:
        if self.create.failure is not None:
            return self.create.failure
        return self.primary if self.primary is not None else self.drop.failure


class CommandFailure(RuntimeError):
    def __init__(self, *, source: str) -> None:
        super().__init__(f"{source} unavailable")
        self.source = source


@dataclass(slots=True, kw_only=True, frozen=True)
class FailingAction:
    source: str = "source"

    def __call__(self, *args: object, **kwargs: object) -> object:
        raise CommandFailure(source=self.source)


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordingAction:
    events: StringIO
    name: str
    result: object = None
    failure: Exception | None = None

    def __call__(self, *args: object, **kwargs: object) -> object:
        self.events.write(f"{self.name}\n")
        if self.failure is not None:
            raise self.failure
        return self.result


@dataclass(slots=True, kw_only=True, frozen=True)
class RepairConnection:
    events: StringIO

    def commit(self) -> None:
        self.events.write("commit\n")

    def rollback(self) -> None:
        self.events.write("rollback\n")

    def close(self) -> None:
        self.events.write("close\n")


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandCase:
    module: ModuleType
    action: str


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandInvocation:
    module: ModuleType
    argv: tuple[str, ...]


type HistoricalMode = Literal["preview", "apply", "coverage"]


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandModeScenario:
    argv: tuple[str, ...]
    events: StringIO
    expected_mode: HistoricalMode


@dataclass(slots=True, kw_only=True, frozen=True)
class RevisionScenario:
    revision: ModuleType
    context: MigrationContext
    cursor: MigrationCursor


def build_migration_history(*revisions, heads=("head",)):
    return MigrationHistory(revisions=tuple(revisions), heads=heads)


def build_migration_revision(name="revision", *, doc="description", merge=False):
    return MigrationRevision(revision=name, doc=doc, is_merge_point=merge)


@dataclass(slots=True, kw_only=True, frozen=True)
class SnapshotScenario:
    expected: Path
    actual: Path


def build_http_response(status, body, text_body=None):
    if text_body is not None:
        return httpx.Response(status, text=text_body)
    return httpx.Response(status, json=body)


def reject_network_access(*args: object, **kwargs: object) -> None:
    raise AssertionError("unit tests must use a saved response or behavioral fake")

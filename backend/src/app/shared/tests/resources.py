"""Owned resource probes for cleanup failure and ordering scenarios."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Self

from app.config import DatabaseSettings


@dataclass(slots=True, kw_only=True, frozen=True)
class ResourceProbe:
    failures: Mapping[str, BaseException]
    events: list[str] = field(default_factory=list)

    def record_operation(self, name: str) -> None:
        self.events.append(name)
        if (failure := self.failures.get(name)) is not None:
            raise failure

    def commit(self) -> None:
        self.record_operation("commit")

    def rollback(self) -> None:
        self.record_operation("rollback")

    def close(self) -> None:
        self.record_operation("close")

    def dispose(self) -> None:
        self.record_operation("dispose")

    def create_resource(self, *args: object, **kwargs: object) -> Self:
        return self

    def create_sessions(self, *args: object, **kwargs: object) -> Self:
        self.record_operation("sessions")
        return self


@dataclass(slots=True, kw_only=True, frozen=True)
class ResourceFailureScenario:
    probe: ResourceProbe
    primary: BaseException | None
    expected: BaseException
    cause: Exception
    settings: DatabaseSettings

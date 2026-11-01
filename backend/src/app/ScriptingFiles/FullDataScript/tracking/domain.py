"""Immutable invocation and durable-run identity passed into ingestion workers."""

from dataclasses import dataclass, field
from time import monotonic_ns

from app.shared.observability.domain import InvocationContext


@dataclass(slots=True, kw_only=True, frozen=True)
class IngestionContext:
    invocation: InvocationContext
    source: str
    stage: str
    run_id: int | None = None
    started_ns: int = field(default_factory=monotonic_ns)

    @property
    def fields(self) -> dict[str, object]:
        fields = self.invocation.fields | {"source": self.source, "stage": self.stage}
        if self.run_id is not None:
            fields["run_id"] = self.run_id
        return fields

    @property
    def duration_ms(self) -> float:
        return (monotonic_ns() - self.started_ns) / 1_000_000

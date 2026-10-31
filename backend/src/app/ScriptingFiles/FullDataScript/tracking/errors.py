"""Structured ingestion lifecycle failures."""

from collections.abc import Mapping
from types import MappingProxyType


class ConcurrentIngestionError(RuntimeError):
    def __init__(self, *, job_name: str) -> None:
        super().__init__(f"Ingestion job {job_name!r} is already running")
        self.job_name = job_name


class UnknownIngestionSourceError(RuntimeError):
    def __init__(self, *, source_code: str) -> None:
        super().__init__(f"Unknown ingestion data source: {source_code}")
        self.source_code = source_code


class IngestionBatchError(RuntimeError):
    def __init__(
        self, *, stage: str, committed_summary: Mapping[str, int], failure: Exception
    ) -> None:
        batches = committed_summary.get("batches_processed", 0)
        super().__init__(f"{stage} failed after {batches} committed batches: {failure}")
        self.stage = stage
        self.committed_summary = MappingProxyType(dict(committed_summary))
        self.failure = failure

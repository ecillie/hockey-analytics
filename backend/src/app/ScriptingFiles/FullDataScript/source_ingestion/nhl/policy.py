"""NHL job option invariants checked before worker or client acquisition."""

from dataclasses import dataclass

from app.ScriptingFiles.FullDataScript.source_ingestion.errors import OptionsViolation
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.domain import (
    NhlStatsOptions,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class NhlStatsOptionsPolicy:
    options: NhlStatsOptions

    def find_violation(self) -> OptionsViolation | None:
        if (
            self.options.first_season > self.options.last_season
            or self.options.workers < 1
            or self.options.page_size < 1
            or self.options.maximum_pages < 1
        ):
            return OptionsViolation(
                reason="NHL season range, workers, and page size must be valid"
            )
        return None

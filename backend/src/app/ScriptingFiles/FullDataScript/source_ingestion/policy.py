"""Source quality invariants checked before any persistence."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isfinite

from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    DataQualityReport,
    PlayerKind,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.errors import (
    IngestionValidationError,
    RowCountViolation,
    DuplicateRatioViolation,
    RowValueViolation,
    ColumnViolation,
    SeasonCoverageViolation,
    StatConsistencyViolation,
    PayloadViolation,
    OptionsViolation,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.util import (
    parse_number,
    parse_strict_integer,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class DuplicateRatioPolicy:
    maximum: float

    def find_violation(
        self, report: DataQualityReport
    ) -> DuplicateRatioViolation | None:
        if report.duplicate_ratio > self.maximum:
            return DuplicateRatioViolation(
                source=report.source,
                actual=report.duplicate_ratio,
                maximum=self.maximum,
            )
        return None


def find_quality_violation(
    report: DataQualityReport, *, minimum_rows: int, maximum_duplicate_ratio: float
) -> RowCountViolation | DuplicateRatioViolation | None:
    if violation := CountPolicy(
        source=report.source, minimum=minimum_rows
    ).find_violation(report.records_valid):
        return violation
    return DuplicateRatioPolicy(maximum=maximum_duplicate_ratio).find_violation(report)


@dataclass(slots=True, kw_only=True, frozen=True)
class RowPolicy:
    source: str
    required_fields: tuple[str, ...]
    grain_fields: tuple[str, ...]
    season_field: str = "season"
    expected_seasons: tuple[int, ...] = ()
    integer_fields: frozenset[str] = frozenset()
    numeric_fields: frozenset[str] = frozenset()

    def find_row_violation(
        self, row: Mapping[str, object], line: int
    ) -> IngestionValidationError | None:
        missing = tuple(
            field
            for field in self.required_fields
            if row.get(field) is None
            or (isinstance(row.get(field), str) and str(row[field]).strip() == "")
        )
        if len(missing) > 0:
            return RowValueViolation(
                source=self.source,
                row=line,
                field=", ".join(missing),
                reason="has null required fields",
            )
        violations = (
            self.find_numeric_violation(row.get(field), line, field)
            for field in sorted(self.numeric_fields | self.integer_fields)
        )
        if violation := next(
            (value for value in violations if value is not None), None
        ):
            return violation
        season = parse_strict_integer(row.get(self.season_field))
        if season is None or not 1900 <= season <= 2200:
            return RowValueViolation(
                source=self.source,
                row=line,
                field=self.season_field,
                reason=f"has invalid {self.season_field}: {row.get(self.season_field)!r}",
            )
        return None

    def find_numeric_violation(
        self, value: object, line: int, field: str
    ) -> IngestionValidationError | None:
        if value in (None, "", "NA", "N/A"):
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            parsed = Decimal("NaN")
        if not parsed.is_finite() or (
            field in self.integer_fields and parsed != parsed.to_integral_value()
        ):
            number_type = "integer" if field in self.integer_fields else "number"
            return RowValueViolation(
                source=self.source,
                row=line,
                field=field,
                reason=f"must be a finite {number_type}",
            )
        return None


def validate_rows(
    rows: Iterable[Mapping[str, object]], policy: RowPolicy
) -> tuple[tuple[dict[str, object], ...], DataQualityReport]:
    materialized = tuple(dict(row) for row in rows)
    if len(materialized) == 0:
        raise PayloadViolation(source=policy.source, reason="source returned no rows")
    available = set().union(*(row.keys() for row in materialized))
    missing = tuple(sorted(set(policy.required_fields) - available))
    if len(missing) > 0:
        raise ColumnViolation(source=policy.source, columns=missing)
    deduplicated: dict[tuple[str, ...], dict[str, object]] = {}
    seasons: set[int] = set()
    for line, row in enumerate(materialized, start=2):
        if violation := policy.find_row_violation(row, line):
            raise violation
        season = parse_strict_integer(row.get(policy.season_field))
        assert season is not None
        seasons.add(season)
        key = tuple(
            str(integer)
            if field in policy.integer_fields
            and (integer := parse_strict_integer(row.get(field))) is not None
            else str("" if row.get(field) is None else row[field]).strip().upper()
            for field in policy.grain_fields
        )
        deduplicated[key] = row
    missing_seasons = tuple(sorted(set(policy.expected_seasons) - seasons))
    if len(missing_seasons) > 0:
        raise SeasonCoverageViolation(source=policy.source, seasons=missing_seasons)
    valid = tuple(deduplicated.values())
    return valid, DataQualityReport(
        source=policy.source,
        records_read=len(materialized),
        records_valid=len(valid),
        duplicate_records=len(materialized) - len(valid),
        seasons=tuple(sorted(seasons)),
    )


def find_stat_violation(
    kind: PlayerKind, row: Mapping[str, object], *, source: str
) -> StatConsistencyViolation | None:
    fields = (
        ("points", "goals", "assists")
        if kind is PlayerKind.SKATER
        else ("shotsAgainst", "saves", "goalsAgainst")
    )
    total, first, second = (
        parse_number(row.get(field), integer=True) for field in fields
    )
    if (
        total is not None
        and first is not None
        and second is not None
        and total != first + second
    ):
        equation = (
            "points must equal goals plus assists"
            if kind is PlayerKind.SKATER
            else "shotsAgainst must equal saves plus goalsAgainst"
        )
        return StatConsistencyViolation(
            source=source, player_id=row.get("playerId"), equation=equation
        )
    return None


@dataclass(slots=True, kw_only=True, frozen=True)
class CountPolicy:
    source: str
    minimum: int

    def find_violation(self, actual: int) -> RowCountViolation | None:
        if actual < self.minimum:
            return RowCountViolation(
                source=self.source, actual=actual, minimum=self.minimum
            )
        return None


def find_quality_options_violation(
    minimum_rows: int, maximum_duplicate_ratio: float
) -> OptionsViolation | None:
    if (
        minimum_rows < 0
        or not isfinite(maximum_duplicate_ratio)
        or not 0 <= maximum_duplicate_ratio <= 1
    ):
        return OptionsViolation(
            reason="minimum rows must be nonnegative and duplicate ratio must be finite between zero and one"
        )
    return None

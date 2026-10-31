"""Structured source validation failures."""


class IngestionValidationError(ValueError):
    pass


class RowCountViolation(IngestionValidationError):
    def __init__(self, *, source: str, actual: int, minimum: int) -> None:
        self.source = source
        self.actual = actual
        self.minimum = minimum
        super().__init__(f"{source}: only {actual} valid rows; minimum is {minimum}")


class DuplicateRatioViolation(IngestionValidationError):
    def __init__(self, *, source: str, actual: float, maximum: float) -> None:
        self.source = source
        self.actual = actual
        self.maximum = maximum
        super().__init__(
            f"{source}: duplicate ratio {actual:.2%} exceeds {maximum:.2%}"
        )


class RowValueViolation(IngestionValidationError):
    def __init__(self, *, source: str, row: int, field: str, reason: str) -> None:
        self.source = source
        self.row = row
        self.field = field
        self.reason = reason
        super().__init__(f"{source}: row {row} field {field} {reason}")


class ColumnViolation(IngestionValidationError):
    def __init__(self, *, source: str, columns: tuple[str, ...]) -> None:
        self.source = source
        self.columns = columns
        super().__init__(f"{source}: missing required columns: {', '.join(columns)}")


class SeasonCoverageViolation(IngestionValidationError):
    def __init__(self, *, source: str, seasons: tuple[int, ...]) -> None:
        self.source = source
        self.seasons = seasons
        super().__init__(
            f"{source}: historical coverage is missing seasons: {', '.join(map(str, seasons))}"
        )


class StatConsistencyViolation(IngestionValidationError):
    def __init__(self, *, source: str, player_id: object, equation: str) -> None:
        self.source = source
        self.player_id = player_id
        self.equation = equation
        super().__init__(f"{source}: {equation} for player {player_id}")


class PayloadViolation(IngestionValidationError):
    def __init__(self, *, source: str, reason: str) -> None:
        self.source = source
        self.reason = reason
        super().__init__(f"{source}: {reason}")


class PaginationViolation(IngestionValidationError):
    def __init__(self, *, source: str, start: int, reason: str) -> None:
        self.source = source
        self.start = start
        self.reason = reason
        super().__init__(f"{source}: invalid pagination at offset {start}: {reason}")


class OptionsViolation(IngestionValidationError):
    def __init__(self, *, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)

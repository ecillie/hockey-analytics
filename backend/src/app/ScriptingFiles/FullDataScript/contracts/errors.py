"""Structured failures at contract source boundaries."""

from enum import StrEnum, auto

from app.ScriptingFiles.FullDataScript.source_ingestion.errors import (
    IngestionValidationError,
)


class CapSpaceError(RuntimeError):
    pass


class ContractOptionError(ValueError):
    def __init__(self, *, option: str, requirement: str) -> None:
        super().__init__(f"{option} {requirement}")
        self.option = option
        self.requirement = requirement


class CapSpaceParseError(CapSpaceError):
    pass


class MoneyFailure(StrEnum):
    MALFORMED = auto()
    NEGATIVE = auto()
    NONFINITE = auto()
    UNREPRESENTABLE = auto()


class MoneyParseError(CapSpaceParseError):
    def __init__(self, *, value: str, reason: MoneyFailure) -> None:
        super().__init__(f"{reason.value} monetary value: {value!r}")
        self.value = value
        self.reason = reason


class SeasonParseError(CapSpaceParseError):
    def __init__(self, *, value: str) -> None:
        super().__init__(f"malformed season: {value!r}")
        self.value = value


class SigningDateParseError(CapSpaceParseError):
    def __init__(self, *, value: str) -> None:
        super().__init__(f"malformed signing date: {value!r}")
        self.value = value


class DocumentFailure(StrEnum):
    EMPTY = auto()
    UNRECOGNIZED = auto()
    INVALID_PAYLOAD = auto()
    INVALID_SEASONS = auto()
    MISSING_CAP_HIT = auto()


class ContractDocumentError(CapSpaceParseError):
    def __init__(self, *, reason: DocumentFailure, source: str) -> None:
        super().__init__(f"{source} contract source: {reason.value}")
        self.reason = reason
        self.source = source


class ProfileIdentityError(CapSpaceParseError):
    def __init__(self, *, expected: str, actual: str | None) -> None:
        message = (
            "source page does not expose an NHL ID"
            if actual is None
            else f"source page NHL ID {actual!r} does not match requested NHL ID {expected!r}"
        )
        super().__init__(message)
        self.expected = expected
        self.actual = actual


class MissingContractError(CapSpaceError):
    def __init__(self, *, contract_id: int) -> None:
        super().__init__(f"contract {contract_id} disappeared during reconciliation")
        self.contract_id = contract_id


class MissingContractSourceError(CapSpaceError):
    def __init__(self, *, source_code: str) -> None:
        super().__init__(
            f"{source_code} source is not registered; run Alembic upgrade head"
        )
        self.source_code = source_code


class ReconciliationFailure(StrEnum):
    AMBIGUOUS = auto()
    INCOMPATIBLE = auto()
    FOREIGN_PLAYER = auto()


class ContractConflictError(CapSpaceError):
    def __init__(self, *, player_id: int, reason: ReconciliationFailure) -> None:
        super().__init__(
            f"contract reconciliation for player {player_id}: {reason.value}"
        )
        self.player_id = player_id
        self.reason = reason


class ActiveContractError(IngestionValidationError):
    def __init__(self, *, slug: str, failure: CapSpaceParseError) -> None:
        detail = (
            "duplicate or non-contiguous seasons"
            if isinstance(failure, ContractDocumentError)
            and failure.reason is DocumentFailure.INVALID_SEASONS
            else str(failure)
        )
        super().__init__(f"CapWages contract {slug}: {detail}")
        self.slug = slug
        self.failure = failure


class ActiveSeasonSequenceError(IngestionValidationError):
    def __init__(self, *, slug: str, years: tuple[int, ...]) -> None:
        super().__init__(
            f"CapWages contract {slug} has duplicate or non-contiguous seasons"
        )
        self.slug = slug
        self.years = years


class ProfileSlugError(CapSpaceParseError):
    def __init__(self, *, expected: str, actual: str) -> None:
        super().__init__(
            f"CapWages profile slug {actual!r} does not match {expected!r}"
        )
        self.expected = expected
        self.actual = actual


class ActiveSeasonCapError(IngestionValidationError):
    def __init__(self, *, external_id: str, season: int) -> None:
        super().__init__(
            f"CapWages contract {external_id} exceeds the season salary cap"
        )
        self.external_id = external_id
        self.season = season


class ActiveProfileCoverageError(IngestionValidationError):
    def __init__(self, *, ratio: float, minimum: float) -> None:
        super().__init__(
            f"CapWages profile success ratio {ratio:.2%} is below {minimum:.2%}; refusing partial refresh"
        )
        self.ratio = ratio
        self.minimum = minimum

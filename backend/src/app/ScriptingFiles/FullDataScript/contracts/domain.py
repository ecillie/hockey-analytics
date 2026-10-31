"""Immutable contract values with isolated source snapshots."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum, auto

from app.ScriptingFiles.FullDataScript.contracts.util import decode_snapshot


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractSeason:
    season_start_year: int
    cap_hit_cents: int
    base_salary_cents: int | None = None
    signing_bonus_cents: int | None = None
    performance_bonus_cents: int | None = None
    minors_salary_cents: int | None = None
    clause: str | None = None
    owning_team: str | None = None
    is_slide: bool = False
    source_snapshot: str | None = None

    @property
    def source_payload(self) -> dict[str, object] | None:
        return decode_snapshot(self.source_snapshot)


@dataclass(slots=True, kw_only=True, frozen=True)
class ParsedContract:
    contract_type: str | None
    is_entry_level: bool
    total_value_cents: int | None
    term_years: int
    signed_on: date | None
    signing_team: str | None
    expiry_status: str | None
    seasons: tuple[ContractSeason, ...]
    external_id: str | None = None
    source_snapshot: str | None = None

    @property
    def source_payload(self) -> dict[str, object] | None:
        return decode_snapshot(self.source_snapshot)


@dataclass(slots=True, kw_only=True, frozen=True)
class Candidate:
    player_id: int
    first_name: str
    last_name: str
    nhl_id: str | None
    missing_seasons: tuple[int, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class StoredContract:
    contract_id: int
    player_id: int
    signing_team_id: int | None
    total_value_cents: int | None


@dataclass(slots=True, kw_only=True, frozen=True)
class ActivePlayer:
    name: str
    slug: str
    team: str
    position: str
    nationality: str | None
    birth_date: str | None


class ProfileSource(StrEnum):
    CAPSPACE = auto()
    CAPWAGES = auto()


class ProfileStatus(StrEnum):
    FAILED = auto()
    NO_CONTRACTS = auto()
    NO_MATCHING_CONTRACTS = auto()
    NO_NHL_ID = auto()
    NOT_FOUND = auto()
    PARSE_FAILED = auto()
    SUCCEEDED = auto()


class AbsenceReason(StrEnum):
    NO_CONTRACTS = auto()
    NO_NHL_ID = auto()
    NOT_FOUND = auto()


class FailureReason(StrEnum):
    FAILED = auto()
    PARSE_FAILED = auto()


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractsFound:
    first: ParsedContract
    remaining: tuple[ParsedContract, ...] = ()

    @property
    def contracts(self) -> tuple[ParsedContract, ...]:
        return (self.first, *self.remaining)


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractsAbsent:
    reason: AbsenceReason
    detail: str | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class ProfileFailure:
    reason: FailureReason
    detail: str


type ProfileOutcome = ContractsFound | ContractsAbsent | ProfileFailure


@dataclass(slots=True, kw_only=True, frozen=True)
class ProfileResult:
    candidate: Candidate
    url: str
    outcome: ProfileOutcome
    html: str | None = None
    source_code: ProfileSource = ProfileSource.CAPSPACE
    fallback_attempted: bool = False
    primary_status: ProfileStatus | None = None
    fallback_status: ProfileStatus | None = None

    @property
    def contracts(self) -> tuple[ParsedContract, ...]:
        return (
            self.outcome.contracts if isinstance(self.outcome, ContractsFound) else ()
        )

    @property
    def status(self) -> ProfileStatus:
        if (
            isinstance(self.outcome, ContractsAbsent)
            and self.outcome.reason is AbsenceReason.NO_CONTRACTS
            and self.source_code is ProfileSource.CAPWAGES
        ):
            return ProfileStatus.NO_MATCHING_CONTRACTS
        if isinstance(self.outcome, (ContractsAbsent, ProfileFailure)):
            return ProfileStatus(self.outcome.reason.value)
        if self.source_code is ProfileSource.CAPWAGES and not self.covers_target:
            return ProfileStatus.NO_MATCHING_CONTRACTS
        return ProfileStatus.SUCCEEDED

    @property
    def error(self) -> str | None:
        return None if isinstance(self.outcome, ContractsFound) else self.outcome.detail

    @property
    def target_seasons_covered(self) -> frozenset[int]:
        targets = frozenset(self.candidate.missing_seasons)
        return frozenset(
            season.season_start_year
            for contract in self.contracts
            for season in contract.seasons
            if season.season_start_year in targets
        )

    @property
    def covers_target(self) -> bool:
        return len(self.target_seasons_covered) > 0


def parsed_profile(
    *,
    candidate: Candidate,
    url: str,
    contracts: tuple[ParsedContract, ...],
    html: str | None = None,
    source_code: ProfileSource = ProfileSource.CAPSPACE,
    fallback_attempted: bool = False,
    primary_status: ProfileStatus | None = None,
    fallback_status: ProfileStatus | None = None,
) -> ProfileResult:
    outcome = (
        ContractsAbsent(reason=AbsenceReason.NO_CONTRACTS)
        if len(contracts) == 0
        else ContractsFound(first=contracts[0], remaining=contracts[1:])
    )
    return ProfileResult(
        candidate=candidate,
        url=url,
        outcome=outcome,
        html=html,
        source_code=source_code,
        fallback_attempted=fallback_attempted,
        primary_status=primary_status,
        fallback_status=fallback_status,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ActiveContractProfile:
    player: ActivePlayer
    contracts: tuple[ParsedContract, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class ActiveContractSnapshot:
    profiles: tuple[ActiveContractProfile, ...]
    failed_slugs: tuple[str, ...]

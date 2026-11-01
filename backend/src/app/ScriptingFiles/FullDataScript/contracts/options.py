"""Validated options for historical contract ingestion."""

from dataclasses import dataclass, field
import math
from app.ScriptingFiles.FullDataScript.contracts.errors import (
    ContractOptionError as ContractOptionError,
)
from app.ScriptingFiles.FullDataScript.contracts.policy import WorkerLimitPolicy


@dataclass(slots=True, kw_only=True, frozen=True)
class HistoricalContractLimits:
    maximum_workers: int = 8
    maximum_batch_size: int = 1000


@dataclass(slots=True, kw_only=True, frozen=True)
class HistoricalContractOptions:
    first_season: int = 2008
    last_season: int = 2025
    limit: int | None = None
    workers: int = 4
    batch_size: int = 100
    player_id: int | None = None
    nhl_id: str | None = None
    force: bool = False
    limits: HistoricalContractLimits = field(default_factory=HistoricalContractLimits)


def find_option_violation(
    options: HistoricalContractOptions,
) -> ContractOptionError | None:
    if violation := WorkerLimitPolicy(
        maximum_workers=options.limits.maximum_workers
    ).find_violation(options.workers):
        return violation
    if not 1 <= options.batch_size <= options.limits.maximum_batch_size:
        return ContractOptionError(
            option="batch_size",
            requirement=f"must be between 1 and {options.limits.maximum_batch_size}",
        )
    if options.first_season > options.last_season:
        return ContractOptionError(option="season range", requirement="must be ordered")
    if options.limit is not None and options.limit <= 0:
        return ContractOptionError(option="limit", requirement="must be positive")
    if options.player_id is not None and options.player_id <= 0:
        return ContractOptionError(option="player_id", requirement="must be positive")
    if options.nhl_id is not None and (
        not options.nhl_id.isascii()
        or not options.nhl_id.isdigit()
        or int(options.nhl_id) <= 0
    ):
        return ContractOptionError(
            option="nhl_id", requirement="must be a positive integer"
        )
    return None


@dataclass(slots=True, kw_only=True, frozen=True)
class ActiveContractOptions:
    minimum_players: int = 500
    minimum_profile_success_ratio: float = 0.98
    workers: int = 10


def find_active_option_violation(
    options: ActiveContractOptions,
) -> ContractOptionError | None:
    if options.minimum_players <= 0:
        return ContractOptionError(
            option="minimum_players", requirement="must be positive"
        )
    if not 0 <= options.minimum_profile_success_ratio <= 1:
        return ContractOptionError(
            option="minimum_profile_success_ratio",
            requirement="must be between 0 and 1",
        )
    if not 1 <= options.workers <= 10:
        return ContractOptionError(
            option="workers", requirement="must be between 1 and 10"
        )
    return None


@dataclass(slots=True, kw_only=True, frozen=True)
class ProfileHttpOptions:
    capspace_base_url: str = "https://cap-space.com"
    capwages_base_url: str = "https://capwages.com"
    timeout: float = 30.0
    max_attempts: int = 4
    maximum_backoff: float = 8.0
    maximum_retry_after: float = 30.0
    retryable_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)
    capwages_slug_suffixes: tuple[str, ...] = ("", "-1", "-2", "-3")


def find_profile_http_violation(
    options: ProfileHttpOptions,
) -> ContractOptionError | None:
    if options.max_attempts <= 0:
        return ContractOptionError(
            option="max_attempts", requirement="must be positive"
        )
    if not math.isfinite(options.timeout) or options.timeout <= 0:
        return ContractOptionError(
            option="timeout", requirement="must be finite and positive"
        )
    limits = (
        ("maximum_backoff", options.maximum_backoff),
        ("maximum_retry_after", options.maximum_retry_after),
    )
    return next(
        (
            ContractOptionError(
                option=name, requirement="must be finite and nonnegative"
            )
            for name, value in limits
            if not math.isfinite(value) or value < 0
        ),
        None,
    )

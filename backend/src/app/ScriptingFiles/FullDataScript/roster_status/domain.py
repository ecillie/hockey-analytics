"""Immutable values and options for roster synchronization."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum, auto


class RosterStatus(StrEnum):
    ACTIVE = auto()
    MINORS = auto()
    LTIR = auto()
    UNKNOWN = auto()

    @property
    def database_value(self) -> str:
        return self.name


@dataclass(slots=True, kw_only=True, frozen=True)
class ExternalRosterPlayer:
    external_id: str
    full_name: str
    birth_date: date | None = None
    team_external_id: str | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class StoredPlayer:
    id: int
    first_name: str
    last_name: str
    birth_date: date | None
    roster_status: RosterStatus
    nhl_external_id: str | None = None
    ahl_external_id: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


type ExternalRoster = tuple[ExternalRosterPlayer, ...]
type StoredRoster = tuple[StoredPlayer, ...]
type RosterIdentity = tuple[str, date]
type OptionalBirthIdentity = tuple[str, date | None]


@dataclass(slots=True, kw_only=True, frozen=True)
class FetchResult:
    items: ExternalRoster = ()
    errors: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return len(self.errors) == 0


@dataclass(slots=True, kw_only=True, frozen=True)
class SyncSummary:
    statuses_updated: int
    active_count: int
    minors_count: int
    ltir_count: int
    unknown_count: int
    preserved_count: int
    nhl_complete: bool
    ahl_complete: bool
    errors: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class HttpOptions:
    timeout_seconds: float = 15.0
    user_agent: str = "TradeValueRosterSync/1.0"


@dataclass(slots=True, kw_only=True, frozen=True)
class NhlFeedOptions:
    standings_url: str = "https://api-web.nhle.com/v1/standings/now"
    roster_url: str = "https://api-web.nhle.com/v1/roster/{team}/current"


@dataclass(slots=True, kw_only=True, frozen=True)
class AhlFeedOptions:
    feed_url: str = "https://lscluster.hockeytech.com/feed/index.php"
    feed_key: str = "ccb91f29d6744675"
    season_id: str | None = None

"""Bounded NHL fetching and validation, separated from SQL writes."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import AbstractContextManager
from dataclasses import dataclass
from itertools import product
from typing import Protocol, runtime_checkable

from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    NhlStatsSummary,
    PlayerKind,
    Player,
    RosterPlayer,
    RosterSummary,
    StatRow,
    StatLayout,
    Team,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.errors import (
    PaginationViolation,
    PayloadViolation,
    OptionsViolation,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.http import SourceClient
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import stat_layout
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.domain import (
    NhlRosterOptions,
    NhlRosterSnapshot,
    NhlStatsOptions,
    NhlStatsSnapshot,
    StatsJob,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.policy import (
    stat_violation,
    CountPolicy,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.schemas import (
    GoalieStatRow,
    SkaterStatRow,
    StatsPage,
    Standings,
    Roster,
    validate_payload,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.util import (
    normalize_nationality,
    parse_number,
    ordered_team_abbreviations,
    normalize_position,
    source_row_hash,
)


type SourceClientFactory = Callable[[], AbstractContextManager[SourceClient]]


@runtime_checkable
class NhlStatsRepository(Protocol):
    def persist(self, snapshot: NhlStatsSnapshot) -> NhlStatsSummary: ...


@runtime_checkable
class NhlRosterRepository(Protocol):
    def persist(self, snapshot: NhlRosterSnapshot) -> RosterSummary: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class NhlStatsService:
    client_factory: SourceClientFactory
    repository: NhlStatsRepository
    options: NhlStatsOptions

    def ingest(self) -> NhlStatsSummary:
        if (
            self.options.first_season > self.options.last_season
            or self.options.workers < 1
            or self.options.page_size < 1
            or self.options.maximum_pages < 1
        ):
            raise OptionsViolation(
                reason="NHL season range, workers, and page size must be valid"
            )
        jobs = (
            StatsJob(kind=kind, season=season, game_type=game_type)
            for kind, season, game_type in product(
                PlayerKind,
                range(self.options.first_season, self.options.last_season + 1),
                (2, 3),
            )
        )
        rows: list[StatRow] = []
        with ThreadPoolExecutor(max_workers=self.options.workers) as executor:
            futures = {executor.submit(self.fetch_job, job): job for job in jobs}
            for future in as_completed(futures):
                rows.extend(future.result())
        return self.repository.persist(NhlStatsSnapshot(rows=tuple(rows)))

    def fetch_job(self, job: StatsJob) -> tuple[StatRow, ...]:
        with self.client_factory() as client:
            raw = fetch_stats_pages(
                client, job, self.options.page_size, self.options.maximum_pages
            )
        if len(raw) == 0:
            raise PayloadViolation(
                source=f"NHL {job.kind} stats",
                reason=f"are incomplete for {job.season}/{job.game_type}",
            )
        layout = stat_layout(job.kind, advanced=False)
        return tuple(normalize_stat_row(row, job, layout) for row in raw)


def fetch_stats_pages(
    client: SourceClient, job: StatsJob, page_size: int = 100, maximum_pages: int = 1000
) -> tuple[dict[str, object], ...]:
    source = f"NHL {job.kind} {job.season}/{job.game_type}"
    rows: list[dict[str, object]] = []
    start = 0
    more = True
    expected_total: int | None = None
    page_count = 0
    while more and page_count < maximum_pages:
        page_count += 1
        raw = client.get_json(
            f"https://api.nhle.com/stats/rest/en/{job.kind}/summary",
            params={
                "isAggregate": "false",
                "isGame": "false",
                "start": start,
                "limit": page_size,
                "cayenneExp": f"seasonId={job.season}{job.season + 1} and gameTypeId={job.game_type}",
            },
        )
        if not isinstance(raw, dict) or not isinstance(raw.get("data"), list):
            raise PayloadViolation(source=source, reason="data must be a list")
        page = validate_payload(raw, StatsPage, source=source)
        if page.total is not None:
            if expected_total is not None and page.total != expected_total:
                raise PaginationViolation(
                    source=source, start=start, reason="total changed between pages"
                )
            expected_total = page.total
        if len(page.data) > page_size:
            raise PaginationViolation(
                source=source, start=start, reason="page exceeds requested limit"
            )
        invalid = next(
            (
                index
                for index, row in enumerate(page.data)
                if row.get("playerId") in (None, "")
            ),
            None,
        )
        if invalid is not None:
            raise PayloadViolation(
                source=source, reason=f"row {invalid} is missing playerId"
            )
        if (
            len(page.data) == 0
            and expected_total is not None
            and start < expected_total
        ):
            raise PaginationViolation(
                source=source, start=start, reason="empty page before total was reached"
            )
        rows.extend(page.data)
        start += len(page.data)
        if expected_total is not None and start > expected_total:
            raise PaginationViolation(
                source=source, start=start, reason="received more rows than total"
            )
        more = len(page.data) > 0 and (
            start < expected_total
            if expected_total is not None
            else len(page.data) == page_size
        )
    if more:
        raise PaginationViolation(
            source=source, start=start, reason="page limit exceeded"
        )
    return tuple(rows)


def normalize_stat_row(
    raw: dict[str, object], job: StatsJob, layout: StatLayout
) -> StatRow:
    source = f"NHL {job.kind} {job.season}/{job.game_type}"
    value = validate_payload(
        raw,
        SkaterStatRow if job.kind == PlayerKind.SKATER else GoalieStatRow,
        source=source,
    )
    if violation := stat_violation(job.kind, raw, source=source):
        raise violation
    return StatRow(
        kind=job.kind,
        external_id=str(raw["playerId"]),
        season=job.season,
        name=next(
            (
                name
                for name in (value.skaterFullName, value.goalieFullName, value.lastName)
                if name is not None and name != ""
            ),
            "Unknown",
        ),
        position=normalize_position(value.positionCode, job.kind == PlayerKind.GOALIE),
        shoots_catches=value.shootsCatches,
        teams=ordered_team_abbreviations(value.teamAbbrevs),
        game_type=job.game_type,
        situation=None,
        metrics=tuple(
            parse_number(raw.get(spec.source_field), spec.integer)
            for spec in layout.metrics
        ),
        source_row_hash=source_row_hash(raw),
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class NhlRosterService:
    client: SourceClient
    repository: NhlRosterRepository
    options: NhlRosterOptions

    def ingest(self) -> RosterSummary:
        standings = validate_payload(
            self.client.get_json("https://api-web.nhle.com/v1/standings/now"),
            Standings,
            source="NHL rosters",
        )
        teams = tuple(
            Team(
                abbreviation=str(row.teamAbbrev),
                name=row.teamName,
                city=row.placeName,
            )
            for row in standings.standings
        )
        unique = {team.abbreviation: team for team in teams}
        if violation := CountPolicy(
            source="NHL rosters teams", minimum=self.options.minimum_teams
        ).find_violation(len(unique)):
            raise violation
        players: list[RosterPlayer] = []
        for abbreviation in unique:
            roster = validate_payload(
                self.client.get_json(
                    f"https://api-web.nhle.com/v1/roster/{abbreviation}/current"
                ),
                Roster,
                source=f"NHL roster {abbreviation}",
            )
            groups = (
                (False, roster.forwards),
                (False, roster.defensemen),
                (True, roster.goalies),
            )
            players.extend(
                RosterPlayer(
                    team=abbreviation,
                    birth_country=row.birthCountry,
                    player=Player(
                        external_id=str(row.id),
                        name=roster_player_name(row.firstName, row.lastName),
                        birth_date=row.birthDate.isoformat()
                        if row.birthDate is not None
                        else None,
                        position=normalize_position(row.positionCode, goalie),
                        shoots_catches=row.shootsCatches,
                        nationality=normalize_nationality(row.birthCountry),
                    ),
                )
                for goalie, group in groups
                for row in group
            )
        if violation := CountPolicy(
            source="NHL rosters players", minimum=self.options.minimum_active_players
        ).find_violation(len(players)):
            raise violation
        return self.repository.persist(
            NhlRosterSnapshot(
                season=self.options.season,
                teams=tuple(unique.values()),
                players=tuple(players),
            )
        )


def roster_player_name(first_name: str | None, last_name: str | None) -> str:
    first = "" if first_name is None else first_name
    last = "" if last_name is None else last_name
    return f"{first} {last}".strip()

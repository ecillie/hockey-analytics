"""Schedule pagination and regular-season validation before writes."""

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    Game,
    ScheduleSummary,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.policy import CountPolicy
from app.ScriptingFiles.FullDataScript.source_ingestion.errors import (
    PaginationViolation,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.http import SourceClient
from app.ScriptingFiles.FullDataScript.source_ingestion.schemas import (
    SchedulePage,
    ScheduleGame,
    validate_payload,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.schedule.domain import (
    ScheduleOptions,
    ScheduleSnapshot,
)


@runtime_checkable
class ScheduleRepository(Protocol):
    def persist(self, snapshot: ScheduleSnapshot) -> ScheduleSummary: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class ScheduleService:
    client: SourceClient
    repository: ScheduleRepository
    options: ScheduleOptions

    def ingest(self) -> ScheduleSummary:
        cursor_date: date | None = date(self.options.season, 10, 1)
        games: dict[int, Game] = {}
        records_read = 0
        while cursor_date is not None:
            source = f"NHL schedule {self.options.season}"
            page = validate_payload(
                self.client.get_json(
                    f"https://api-web.nhle.com/v1/schedule/{cursor_date.isoformat()}"
                ),
                SchedulePage,
                source=source,
            )
            normalized = parse_schedule_page(page, source=source)
            records_read += len(normalized)
            games.update((game.external_id, game) for game in normalized)
            next_date = page.nextStartDate
            if next_date is not None and next_date <= cursor_date:
                raise PaginationViolation(
                    source=source,
                    start=records_read,
                    reason="nextStartDate must advance",
                )
            cursor_date = (
                next_date
                if next_date is not None and next_date.year <= self.options.season + 1
                else None
            )
        if violation := CountPolicy(
            source=f"NHL schedule {self.options.season} games",
            minimum=self.options.minimum_games,
        ).find_violation(len(games)):
            raise violation
        return self.repository.persist(
            ScheduleSnapshot(
                season=self.options.season,
                games=tuple(games.values()),
                records_read=records_read,
            )
        )


def parse_schedule_page(page: SchedulePage, *, source: str) -> tuple[Game, ...]:
    rows = (
        (day.date, raw)
        for day in page.gameWeek
        for raw in day.games
        if raw.get("gameType") == 2
    )
    return tuple(
        parse_schedule_game(game_date, raw, source=source) for game_date, raw in rows
    )


def parse_schedule_game(
    game_date: date, raw: dict[str, object], *, source: str
) -> Game:
    value = validate_payload(raw, ScheduleGame, source=source)
    return Game(
        external_id=value.id,
        game_date=game_date,
        away_team=value.awayTeam.abbrev,
        home_team=value.homeTeam.abbrev,
        start_time_utc=value.startTimeUTC,
        venue=value.venue,
        game_state=value.gameState,
        away_score=value.awayTeam.score,
        home_score=value.homeTeam.score,
    )

"""NHL standings and roster adapter over an injected HTTP client."""

from dataclasses import dataclass, field

from app.ScriptingFiles.FullDataScript.roster_status.domain import (
    ExternalRosterPlayer,
    FetchResult,
    NhlFeedOptions,
)
from app.ScriptingFiles.FullDataScript.roster_status.errors import FeedFetchError
from app.ScriptingFiles.FullDataScript.roster_status.http_json_client import (
    JsonClient,
    fetch_validated,
)
from app.ScriptingFiles.FullDataScript.roster_status.schemas import (
    NhlRoster,
    NhlStandings,
)
from app.ScriptingFiles.FullDataScript.roster_status.util import (
    parse_nhl_roster,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class NhlRosterService:
    http_client: JsonClient
    options: NhlFeedOptions = field(default_factory=NhlFeedOptions)

    def fetch_current_rosters(self) -> FetchResult:
        try:
            standings = fetch_validated(
                self.http_client,
                self.options.standings_url,
                NhlStandings,
                "NHL team list",
            )
        except FeedFetchError as exc:
            return FetchResult(errors=(str(exc),))
        teams = sorted(
            {
                row.teamAbbrev.default
                for row in standings.standings
                if row.teamAbbrev.default != ""
            }
        )
        if len(teams) == 0:
            return FetchResult(errors=("NHL standings returned no teams",))
        players: list[ExternalRosterPlayer] = []
        errors: list[str] = []
        for team in teams:
            try:
                payload = fetch_validated(
                    self.http_client,
                    self.options.roster_url.format(team=team),
                    NhlRoster,
                    f"NHL roster for {team}",
                )
                players.extend(parse_nhl_roster(payload, team))
            except FeedFetchError as exc:
                errors.append(str(exc))
        return FetchResult(items=tuple(players), errors=tuple(errors))

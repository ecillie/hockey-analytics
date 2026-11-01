"""HockeyTech roster adapter with explicit key and season configuration."""

from dataclasses import dataclass, field

from app.ScriptingFiles.FullDataScript.roster_status.domain import (
    AhlFeedOptions,
    ExternalRosterPlayer,
    FetchResult,
)
from app.ScriptingFiles.FullDataScript.roster_status.errors import FeedFetchError
from app.ScriptingFiles.FullDataScript.roster_status.http_json_client import (
    JsonClient,
    fetch_validated,
)
from app.ScriptingFiles.FullDataScript.roster_status.schemas import (
    AhlBootstrap,
    AhlRoster,
)
from app.ScriptingFiles.FullDataScript.roster_status.util import (
    parse_ahl_roster,
    index_ahl_players,
)


def build_feed_params(options: AhlFeedOptions) -> dict[str, str]:
    return {
        "feed": "statviewfeed",
        "key": options.feed_key,
        "client_code": "ahl",
        "site_id": "0",
        "lang": "en",
        "callback": "JSON_CALLBACK",
    }


@dataclass(slots=True, kw_only=True, frozen=True)
class AhlRosterService:
    http_client: JsonClient
    options: AhlFeedOptions = field(default_factory=AhlFeedOptions)

    def fetch_current_rosters(self) -> FetchResult:
        params = {
            **build_feed_params(self.options),
            "view": "bootstrap",
            "season": "latest"
            if self.options.season_id is None
            else self.options.season_id,
            "pageName": "roster",
            "league_id": "4",
        }
        try:
            bootstrap = fetch_validated(
                self.http_client,
                self.options.feed_url,
                AhlBootstrap,
                "AHL roster bootstrap",
                params,
            )
        except FeedFetchError as exc:
            return FetchResult(errors=(str(exc),))
        season_id = (
            self.options.season_id
            if self.options.season_id is not None
            else bootstrap.current_season_id
        )
        if season_id is None:
            return FetchResult(
                errors=("AHL roster bootstrap returned no current season",)
            )
        teams = tuple(
            str(team.id)
            for team in bootstrap.teamsNoAll
            if str(team.id) not in {"", "-1"}
        )
        if len(teams) == 0:
            return FetchResult(errors=("AHL roster bootstrap returned no teams",))
        players: list[ExternalRosterPlayer] = []
        errors: list[str] = []
        for team in teams:
            roster_params = {
                **build_feed_params(self.options),
                "view": "roster",
                "team_id": team,
                "season_id": str(season_id),
                "league_id": str(bootstrap.current_league_id),
            }
            try:
                payload = fetch_validated(
                    self.http_client,
                    self.options.feed_url,
                    AhlRoster,
                    f"AHL roster for team {team}",
                    roster_params,
                )
                players.extend(parse_ahl_roster(payload, team))
            except FeedFetchError as exc:
                errors.append(str(exc))
        indexed = index_ahl_players(tuple(players))
        conflicts = {player.external_id for player in players} - indexed.keys()
        errors.extend(
            f"AHL feed has conflicting profiles for external ID {external_id}"
            for external_id in sorted(conflicts)
        )
        return FetchResult(items=tuple(indexed.values()), errors=tuple(errors))

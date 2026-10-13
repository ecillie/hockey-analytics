"""NHL reference/profile/roster/statistics operations shared by setup and refresh."""
from dataclasses import dataclass
from urllib.parse import urlencode
from uuid import NAMESPACE_URL, uuid5

from app.jobs.shared.execution import JobOperation
from app.jobs.shared.identity import UnresolvedIdentity
from app.jobs.shared.normalization import iso_date, seconds
from .common import (batches, localized, nhl_identity, positive_id, scan,
                     source_record, stable_id, team_scope_ready)

STATS = "https://api.nhle.com/stats/rest/en"
WEB = "https://api-web.nhle.com/v1"


def season_id(year):
    return year * 10000 + year + 1


def season_year(value):
    value = positive_id(value)
    year, end = divmod(value, 10000)
    if end != year + 1:
        raise ValueError("Malformed NHL season ID")
    return year


def json_get(ctx, url):
    if ctx.client is None:
        raise ValueError("NHL collection requires a configured SourceClient")
    data = ctx.client.json("nhl", url)
    if not isinstance(data, dict):
        raise ValueError("NHL response is not an object")
    return data


def paged(ctx, path, expression=None):
    """Use independent source totals, bounded pages, stable ordering and identities."""
    result, start, expected = [], 0, None
    size = min(100, ctx.config.max_batch_records)
    for _ in range(ctx.config.max_batches):
        params = {"start": start, "limit": size}
        if expression is not None:
            params.update(isAggregate="false", isGame="false", cayenneExp=expression,
                          sort='[{"property":"' + ("teamId" if path.startswith("team/") else "playerId") + '","direction":"ASC"}]')
        page = json_get(ctx, f"{STATS}/{path}?{urlencode(params)}")
        rows, total = page.get("data"), page.get("total")
        if (not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
                or type(total) is not int or total < 0 or len(rows) > size):
            raise ValueError("NHL enumeration lacks valid data/total")
        if expected is not None and expected != total:
            raise ValueError("NHL population changed during pagination")
        expected = total
        result.extend(rows)
        start += len(rows)
        if start == total:
            return result
        if not rows or start > total:
            raise ValueError("NHL enumeration is incomplete")
    raise ValueError("NHL pagination exceeds configured limit")


def summaries(ctx, kind, year, game_type, team_id=None):
    expression = f"seasonId={season_id(year)} and gameTypeId={game_type}"
    if team_id is not None:
        expression += f" and teamId={team_id}"
    rows = paged(ctx, f"{kind}/summary", expression)
    field = "teamId" if kind == "team" else "playerId"
    ids = set()
    for row in rows:
        identity = positive_id(row[field])
        if (identity in ids or season_year(row["seasonId"]) != year
                or row.get("gameTypeId", game_type) != game_type):
            raise ValueError("Duplicate or out-of-scope NHL summary")
        ids.add(identity)
    return rows


def roster(ctx, abbreviation, year, *, current=False):
    data = json_get(ctx, f"{WEB}/roster/{abbreviation}/{ 'current' if current else season_id(year)}")
    if any(not isinstance(data.get(group), list) for group in ("forwards", "defensemen", "goalies")):
        raise ValueError("Roster response lacks a complete positional enumeration")
    players = data["forwards"] + data["defensemen"] + data["goalies"]
    ids = [positive_id(row["id"]) for row in players]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate NHL roster player")
    # An empty roster is unavailable, never proof that the team has no players.
    if not players:
        raise ValueError("NHL roster is unavailable/empty")
    return data, players


def canonical_team_id(ctx, nhl_id):
    existing = ctx.find_unique("teams", ("nhl_team_id",), (nhl_id,))
    if existing is None and ctx.lookup("teams", (nhl_id,)) is not None:
        raise UnresolvedIdentity("NHL team ID collides with an existing canonical identity; review required")
    return existing.team_id if existing else nhl_id


def collect_references(ctx, cursor):
    raw_teams = paged(ctx, "team")
    franchises = paged(ctx, "franchise")
    seasons = paged(ctx, "season")
    for rows in (raw_teams, franchises, seasons):
        identities = [positive_id(row["id"]) for row in rows]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate NHL reference identities")
    teams = {positive_id(row["id"]): row for row in raw_teams
             if row["id"] not in (70, 99) and row.get("leagueId", 133) == 133}
    known = {season_year(row["id"]): row for row in seasons}
    requested = range(ctx.config.first_season, ctx.config.last_season + 1)
    if any(year not in known for year in requested):
        raise ValueError("Requested NHL season is unavailable")
    participation = {}
    for year in set(requested) | {ctx.config.current_season}:
        scope = {}
        for game_type in ctx.config.game_types:
            for row in summaries(ctx, "team", year, game_type):
                scope[positive_id(row["teamId"])] = row
        participation[year] = scope
    standings = json_get(ctx, f"{WEB}/standings/now").get("standings")
    if not isinstance(standings, list) or not standings:
        raise ValueError("Current NHL team references are unavailable")
    current = {}
    for standing in standings:
        if season_year(standing["seasonId"]) != ctx.config.current_season or standing.get("gameTypeId", 2) != 2:
            raise ValueError("Current NHL standings differ from the requested season/type")
        abbreviation, name = localized(standing["teamAbbrev"]), localized(standing["teamName"])
        matches = [nhl_id for nhl_id, team in teams.items()
                   if team["triCode"] == abbreviation and team["fullName"] == name]
        if len(matches) != 1 or matches[0] in current:
            raise ValueError("Ambiguous/duplicate current NHL team reference")
        current[matches[0]] = {"teamId": matches[0], "seasonId": standing["seasonId"],
                               "teamFullName": name, "standing": standing}
    # Games played alone cannot determine the full current team population.
    participation[ctx.config.current_season] = current
    items = []
    for raw in franchises:
        payload = {"franchise_id": positive_id(raw["id"]), "name": localized(raw["fullName"])}
        items.append(source_record(ctx, "franchises", payload, source="nhl", key=raw["id"], raw=raw))
    for nhl_id, raw in sorted(teams.items()):
        team_id = canonical_team_id(ctx, nhl_id)
        previous = ctx.lookup("teams", (team_id,))
        franchise_id = positive_id(raw["franchiseId"]) if raw.get("franchiseId") is not None else previous.franchise_id if previous else None
        payload = {"team_id": team_id, "nhl_team_id": nhl_id,
                   "name": localized(raw["fullName"]), "abbreviation": localized(raw["triCode"]),
                   "active": nhl_id in current, "franchise_id": franchise_id}
        items.append(source_record(ctx, "teams", payload, source="nhl", key=nhl_id, raw=raw))
    for year in requested:
        payload = {"season": year, "end_year": year + 1, "label": f"{year}-{str(year+1)[2:]}"}
        items.append(source_record(ctx, "seasons", payload, source="nhl", key=year, raw=known[year]))
        if not participation[year]:
            raise ValueError(f"NHL team-season coverage unavailable for {year}")
        for nhl_id, raw in sorted(participation[year].items()):
            team = teams[nhl_id]
            previous = ctx.lookup("teams", (canonical_team_id(ctx, nhl_id),))
            franchise_id = positive_id(team["franchiseId"]) if team.get("franchiseId") is not None else previous.franchise_id if previous else None
            payload = {"team_id": canonical_team_id(ctx, nhl_id), "season": year,
                       "name": localized(raw.get("teamFullName", team["fullName"])),
                       "abbreviation": localized(team["triCode"]),
                       "franchise_id": franchise_id}
            items.append(source_record(ctx, "team_seasons", payload, source="nhl", key=f"{year}/{nhl_id}", raw=raw))
    yield from batches(ctx, items, cursor, partition="nhl-references")


@dataclass(frozen=True)
class Discovery:
    """Additional NHL IDs discovered by dependent sources; no name-only matches."""
    player_ids: tuple[int, ...] = ()
    include_game_participation: bool = True


def collect_profiles(ctx, cursor, discovery=Discovery()):
    ids = {positive_id(value) for value in discovery.player_ids}
    ids.update(player.nhl_player_id for player in scan(ctx, "player_profiles") if player.nhl_player_id)
    for year in range(ctx.config.first_season, ctx.config.last_season + 1):
        for game_type in ctx.config.game_types:
            for kind in ("skater", "goalie"):
                ids.update(positive_id(row["playerId"]) for row in summaries(ctx, kind, year, game_type))
        for team in scan(ctx, "team_seasons", season=year):
            _, players = roster(ctx, team.abbreviation, year, current=year == ctx.config.current_season)
            ids.update(positive_id(row["id"]) for row in players)
    if discovery.include_game_participation:
        for game in scan(ctx, "games"):
            if (game.status != "FINAL" or game.game_type not in ctx.config.game_types
                    or not ctx.config.first_season <= game.season <= ctx.config.last_season):
                continue
            box = json_get(ctx, f"{WEB}/gamecenter/{game.nhl_game_id}/boxscore")
            if positive_id(box["id"]) != game.nhl_game_id:
                raise ValueError("Boxscore returned a different game")
            for side in ("homeTeam", "awayTeam"):
                groups = box["playerByGameStats"][side]
                for group in ("forwards", "defense", "goalies"):
                    if not isinstance(groups.get(group), list):
                        raise ValueError("Incomplete boxscore participation")
                    ids.update(positive_id(row["playerId"]) for row in groups[group])
    items = []
    for nhl_id in sorted(ids):
        raw = json_get(ctx, f"{WEB}/player/{nhl_id}/landing")
        if positive_id(raw["playerId"]) != nhl_id:
            raise ValueError("Player landing returned a different NHL identity")
        existing = ctx.find_unique("player_profiles", ("nhl_player_id",), (nhl_id,))
        if existing is None and ctx.lookup("player_profiles", (nhl_id,)) is not None:
            raise UnresolvedIdentity("NHL player ID collides with an existing canonical identity; review required")
        payload = {"player_id": existing.player_id if existing else nhl_id, "nhl_player_id": nhl_id,
                   "first_name": localized(raw["firstName"]), "last_name": localized(raw["lastName"]),
                   "active": raw["isActive"], "birth_date": iso_date(raw.get("birthDate")),
                   "position": {"L": "LW", "R": "RW"}.get(raw.get("position"), raw.get("position")),
                   "nationality": raw.get("birthCountry"), "shoots_catches": raw.get("shootsCatches")}
        items.append(source_record(ctx, "player_profiles", payload, source="nhl", key=nhl_id, raw=raw))
    yield from batches(ctx, items, cursor, partition="nhl-profiles")


def collect_rosters(ctx, cursor):
    items = []
    for year in range(ctx.config.first_season, ctx.config.last_season + 1):
        for team in scan(ctx, "team_seasons", season=year):
            raw, players = roster(ctx, team.abbreviation, year, current=year == ctx.config.current_season)
            snapshot = uuid5(NAMESPACE_URL, f"{ctx.run.run_id}/roster/{team.team_id}/{year}")
            for player in players:
                candidate = {"nhl_id": player["id"], "team_id": team.team_id, "season": year,
                             "snapshot_id": snapshot}
                items.append(source_record(ctx, "memberships", candidate, source="nhl",
                    key=f"{year}/{team.team_id}/{player['id']}", raw=player))
                if year == ctx.config.current_season:
                    profile = ctx.find_unique("player_profiles", ("nhl_player_id",), (positive_id(player["id"]),))
                    record_scope = {"record_key": [str(snapshot), profile.player_id, team.team_id]} if profile else {}
                    items.append(source_record(ctx, "roster_observations", candidate, source="nhl",
                        key=f"{year}/{team.team_id}/{player['id']}", raw=raw, scope=record_scope))
    yield from batches(ctx, items, cursor, partition="nhl-rosters")


def normalize_roster(item, ctx):
    row = item.payload
    player_id = nhl_identity(ctx, "player", row["nhl_id"])
    if item.dataset == "memberships":
        return {"membership_id": stable_id("nhl-membership", player_id, row["team_id"], row["season"]),
                "player_id": player_id, "team_id": row["team_id"], "season": row["season"]}
    return {"snapshot_id": row["snapshot_id"], "player_id": player_id, "team_id": row["team_id"],
            "observed_at": ctx.run.started_at, "complete_scope": True, "source": "nhl"}


def collect_stats(ctx, cursor):
    items = []
    for year in range(ctx.config.first_season, ctx.config.last_season + 1):
        for game_type in ctx.config.game_types:
            for kind in ("skater", "goalie"):
                # Source TOTAL and TEAM rows have separate grains, including trades.
                for team in (None, *scan(ctx, "team_seasons", season=year)):
                    nhl_team_id = ctx.lookup("teams", (team.team_id,)).nhl_team_id if team else None
                    for raw in summaries(ctx, kind, year, game_type, nhl_team_id):
                        payload = {"raw": raw, "season": year, "game_type": game_type,
                                   "stat_kind": kind, "team_id": team.team_id if team else None}
                        items.append(source_record(ctx, "basic_stats", payload, source="nhl",
                            key=f"{year}/{game_type}/{kind}/{nhl_team_id}/{raw['playerId']}", raw=raw))
    yield from batches(ctx, items, cursor, partition="nhl-basic-stats")


def normalize_stats(item, ctx):
    row, raw = item.payload, item.payload["raw"]
    result = {"player_id": nhl_identity(ctx, "player", raw["playerId"]), "source": "nhl",
              "season": row["season"], "game_type": row["game_type"], "team_id": row["team_id"],
              "team_scope": "TOTAL" if row["team_id"] is None else "TEAM", "stat_kind": row["stat_kind"],
              "games_played": raw["gamesPlayed"]}
    fields = {"goals": "goals", "assists": "assists", "points": "points", "plus_minus": "plusMinus",
              "penalty_minutes": "penaltyMinutes", "power_play_goals": "ppGoals", "power_play_points": "ppPoints",
              "short_handed_goals": "shGoals", "shots": "shots", "shooting_percentage": "shootingPct",
              "wins": "wins", "losses": "losses", "overtime_losses": "otLosses", "saves": "saves",
              "shots_against": "shotsAgainst", "goals_against": "goalsAgainst", "shutouts": "shutouts",
              "save_percentage": "savePct", "goals_against_average": "goalsAgainstAverage"}
    result.update({field: raw[source] for field, source in fields.items() if source in raw})
    if raw.get("timeOnIce") is not None:
        value = raw["timeOnIce"]
        if isinstance(value, str):
            result["time_on_ice"] = seconds(value)
        elif type(value) in (int, float):
            result["time_on_ice"] = float(value)
        else:
            raise ValueError("NHL total TOI must be explicit seconds or MM:SS")
    # Rounded per-game TOI is not an exact total; missing totals stay None.
    return result


@dataclass(frozen=True)
class MappingCandidate:
    source: str
    entity_type: str
    source_id: str
    nhl_id: int
    evidence: str

    def __post_init__(self):
        if (self.entity_type not in ("player", "team")
                or not all(isinstance(value, str) and value.strip() for value in (self.source, self.source_id, self.evidence))):
            raise ValueError("Source mappings need player/team IDs and retained decision evidence")
        positive_id(self.nhl_id)


def collect_mappings(ctx, cursor, candidates=()):
    items = []
    for dataset, entity, field in (("teams", "team", "nhl_team_id"), ("player_profiles", "player", "nhl_player_id")):
        for record in scan(ctx, dataset):
            nhl_id = getattr(record, field)
            if nhl_id is None:
                continue
            for source in (("nhl", "capspace") if entity == "player" else ("nhl",)):
                payload = {"source": source, "entity_type": entity, "source_id": str(nhl_id),
                           "canonical_id": getattr(record, f"{entity}_id")}
                items.append(source_record(ctx, "source_mappings", payload, source=source,
                    key=f"{entity}/{nhl_id}", raw={"nhl_id": nhl_id, "evidence": "NHL durable identity"}))
    for candidate in candidates:
        if not candidate.evidence.strip():
            raise ValueError("External mappings require cross-ID or reviewed-decision evidence")
        payload = {"source": candidate.source, "entity_type": candidate.entity_type,
                   "source_id": candidate.source_id, "nhl_id": candidate.nhl_id}
        items.append(source_record(ctx, "source_mappings", payload, source=candidate.source,
            key=f"{candidate.entity_type}/{candidate.source_id}", raw={**payload, "evidence": candidate.evidence}))
    yield from batches(ctx, items, cursor, partition="source-mappings")


def normalize_mapping(item, ctx):
    payload = dict(item.payload)
    if "nhl_id" in payload:
        payload["canonical_id"] = nhl_identity(ctx, payload["entity_type"], payload.pop("nhl_id"))
    existing = ctx.lookup("source_mappings", (payload["source"], payload["entity_type"], payload["source_id"]))
    if existing and existing.canonical_id != payload["canonical_id"]:
        raise UnresolvedIdentity("Conflicting source mapping requires explicit review; it cannot be reassigned")
    return payload


def operations(*, discovery=Discovery(), mappings=()):
    return {
        "teams_seasons": JobOperation(collect_references),
        "player_profiles": JobOperation(lambda ctx, cursor: collect_profiles(ctx, cursor, discovery)),
        "team_rosters": JobOperation(collect_rosters, normalize_roster, ready=team_scope_ready),
        "source_id_mappings": JobOperation(lambda ctx, cursor: collect_mappings(ctx, cursor, mappings),
                                           normalize_mapping, ready=lambda ctx: bool(scan(ctx, "teams")) and bool(scan(ctx, "player_profiles"))),
        "basic_stats": JobOperation(collect_stats, normalize_stats, ready=team_scope_ready),
    }

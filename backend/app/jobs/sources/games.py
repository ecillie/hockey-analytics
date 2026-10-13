"""NHL schedule and completed-game facts; no collection on import."""
from datetime import timedelta

from app.jobs.shared.execution import JobOperation
from app.jobs.shared.identity import UnresolvedIdentity
from app.jobs.shared.normalization import seconds, utc_timestamp
from .common import batches, nhl_identity, positive_id, scan, team_scope_ready
from .feed_support import coverage, feed_record, number, unique_rows, cached_batches
from .nhl import WEB, json_get, season_id, season_year

STATES = {"FUT": "SCHEDULED", "PRE": "SCHEDULED", "LIVE": "LIVE", "CRIT": "LIVE",
          "FINAL": "FINAL", "OFF": "FINAL", "PPD": "POSTPONED", "CNCL": "CANCELLED"}
PLAYER_FIELDS = ("scoringPlayerId", "shootingPlayerId", "hittingPlayerId", "blockingPlayerId",
                 "committedByPlayerId", "winningPlayerId", "goalieInNetId", "assist1PlayerId",
                 "assist2PlayerId", "hitteePlayerId", "drawnByPlayerId", "losingPlayerId")


def scoped_games(ctx):
    return tuple(game for game in scan(ctx, "games")
                 if ctx.config.first_season <= game.season <= ctx.config.last_season
                 and game.game_type in ctx.config.game_types)


def game_identity(ctx, nhl_id):
    existing = ctx.find_unique("games", ("nhl_game_id",), (positive_id(nhl_id),))
    if existing is None and ctx.lookup("games", (nhl_id,)) is not None:
        raise UnresolvedIdentity("NHL game ID collides with a canonical identity")
    return existing.game_id if existing else nhl_id


def collect_schedule(ctx, cursor):
    items = []
    for year in range(ctx.config.first_season, ctx.config.last_season + 1):
        rows = []
        for team in scan(ctx, "team_seasons", season=year):
            data = json_get(ctx, f"{WEB}/club-schedule-season/{team.abbreviation}/{season_id(year)}")
            if not isinstance(data.get("games"), list):
                raise ValueError("Schedule lacks explicit game enumeration")
            if "season" in data and season_year(data["season"]) != year:
                raise ValueError("Schedule returned a different season")
            for raw in data["games"]:
                if type(raw.get("gameType")) is not int:
                    raise ValueError("Schedule lacks a valid game type")
                if raw["gameType"] not in ctx.config.game_types:
                    continue
                if season_year(raw["season"]) != year:
                    raise ValueError("Schedule game is outside requested season")
                if ctx.lookup("teams", (team.team_id,)).nhl_team_id not in (raw["homeTeam"]["id"], raw["awayTeam"]["id"]):
                    raise ValueError("Club schedule includes an unrelated game")
                rows.append(raw)
        rows = unique_rows(rows, lambda row: positive_id(row["id"]))
        for game_type in ctx.config.game_types:
            selected = [row for row in rows if row["gameType"] == game_type]
            report = coverage(ctx, "games", season=year, game_type=game_type, enumerated=len(selected),
                limitation="Club schedule enumeration; independent league population audit still required")
            for raw in selected:
                items.append(feed_record(ctx, "games", raw, source="nhl", key=raw["id"], raw=raw, report=report))
    yield from batches(ctx, items, cursor, partition="nhl-schedules")


def normalize_schedule(item, ctx):
    raw = item.payload
    nhl_id = positive_id(raw["id"])
    if nhl_id // 1_000_000 != season_year(raw["season"]) or nhl_id // 10000 % 100 != raw["gameType"]:
        raise ValueError("NHL game ID encodes a different season/type")
    state = STATES.get(raw["gameState"])
    if state is None:
        raise ValueError("Unsupported NHL game state")
    result = {"game_id": game_identity(ctx, raw["id"]), "nhl_game_id": positive_id(raw["id"]),
              "season": season_year(raw["season"]), "game_type": raw["gameType"],
              "home_team_id": nhl_identity(ctx, "team", raw["homeTeam"]["id"]),
              "away_team_id": nhl_identity(ctx, "team", raw["awayTeam"]["id"]),
              "start_time": utc_timestamp(raw["startTimeUTC"]), "status": state,
              "home_score": number(raw["homeTeam"].get("score"), count=True),
              "away_score": number(raw["awayTeam"].get("score"), count=True)}
    if state == "FINAL" and (result["home_score"] is None or result["away_score"] is None):
        raise ValueError("Completed schedule game lacks scores")
    return result


def check_game(data, game):
    if (positive_id(data["id"]) != game.nhl_game_id or season_year(data["season"]) != game.season
            or data["gameType"] != game.game_type or STATES.get(data["gameState"]) != "FINAL"):
        raise ValueError("Completed-game response differs from accepted game identity/state")


def processed_game(ctx, game):
    # Team rows can be committed before a later event batch fails. Only a
    # successfully completed source run establishes prior processing.
    for team in (game.home_team_id, game.away_team_id):
        row = ctx.reader.get("game_stats", (game.game_id, team, "team", team), snapshot=ctx.snapshot)
        run = ctx.lookup("pipeline_runs", (row.run_id,)) if row is not None else None
        if run is None or run.status not in ("succeeded", "no_change"):
            return False
    return True


def detail_records(ctx):
    cutoff = ctx.run.started_at - timedelta(days=ctx.config.correction_lookback_days)
    for game in scoped_games(ctx):
        if game.status != "FINAL":
            continue
        # Unprocessed games are always eligible; lookback rechecks accepted games.
        processed = processed_game(ctx, game)
        if ctx.config.mode == "refresh" and processed and game.start_time < cutoff:
            continue
        box = json_get(ctx, f"{WEB}/gamecenter/{game.nhl_game_id}/boxscore")
        play = json_get(ctx, f"{WEB}/gamecenter/{game.nhl_game_id}/play-by-play")
        check_game(box, game)
        check_game(play, game)
        box_rows = []
        for side, team_id, score in (("homeTeam", game.home_team_id, game.home_score),
                                    ("awayTeam", game.away_team_id, game.away_score)):
            team = ctx.lookup("teams", (team_id,))
            if team is None or any(data[side]["id"] != team.nhl_team_id for data in (box, play)):
                raise ValueError("Game response teams differ from accepted schedule")
            raw_team = box[side]
            if number(raw_team.get("score"), count=True, required=True) != score:
                raise ValueError("Boxscore score differs from schedule; refresh schedule first")
            groups = box["playerByGameStats"][side]
            if any(not isinstance(groups.get(group), list) for group in ("forwards", "defense", "goalies")):
                raise ValueError("Incomplete completed-game boxscore groups")
            players = groups["forwards"] + groups["defense"] + groups["goalies"]
            if not players:
                raise ValueError("Empty completed-game boxscore")
            players = unique_rows(players, lambda row: positive_id(row["playerId"]))
            goals = [number(row.get("goals"), count=True) for row in groups["forwards"] + groups["defense"]]
            shootout = box.get("gameOutcome", {}).get("lastPeriodType") == "SO"
            if goals and all(value is not None for value in goals):
                if sum(goals) != score and not (shootout and sum(goals) == score - 1):
                    raise ValueError("Skater goal total differs from team score")
            box_rows.append((team_id, "team", raw_team))
            box_rows.extend((team_id, "player", raw) for raw in players)
        report = coverage(ctx, "game_stats", season=game.season, game_type=game.game_type,
                          game_id=game.game_id, enumerated=len(box_rows), limitation="Published boxscore fields only")
        for team_id, entity, raw in box_rows:
            payload = {"game_id": game.game_id, "team_id": team_id, "entity_type": entity, "raw": raw}
            ids = (positive_id(raw["playerId"]),) if entity == "player" else ()
            yield feed_record(ctx, "game_stats", payload, source="nhl",
                key=f"{game.nhl_game_id}/{team_id}/{entity}/{ids or team_id}", raw=raw, report=report, player_ids=ids)
        events = play.get("plays")
        if not isinstance(events, list):
            raise ValueError("Play-by-play lacks explicit plays enumeration")
        events = unique_rows(events, lambda row: positive_id(row["eventId"]))
        incoming = {str(positive_id(row["eventId"])) for row in events}
        if any(event.source == "nhl" and event.event_id not in incoming for event in scan(ctx, "game_events", game_id=game.game_id)):
            raise ValueError("NHL removed an accepted event; review required because the contract has no tombstones")
        events = sorted(events, key=lambda row: number(row["sortOrder"], count=True, required=True))
        orders, previous = set(), (0, 0)
        for raw in events:
            order = number(raw["sortOrder"], count=True, required=True)
            period = positive_id(raw["periodDescriptor"]["number"])
            elapsed = seconds(raw["timeInPeriod"])
            if elapsed is None or order in orders or (period, elapsed) < previous:
                raise ValueError("Invalid/repeated event order or backwards game clock")
            kind = raw["periodDescriptor"]["periodType"]
            maximum = 300 if kind == "OT" and game.game_type == 2 else 1200
            if elapsed > maximum or kind not in ("REG", "OT", "SO"):
                raise ValueError("Event clock exceeds period duration")
            orders.add(order)
            previous = period, elapsed
        report = coverage(ctx, "game_events", season=game.season, game_type=game.game_type,
            game_id=game.game_id, enumerated=len(events), status="limited",
            event_types=sorted({raw["typeDescKey"] for raw in events}),
            coordinate_records=sum(raw.get("details", {}).get("xCoord") is not None and
                                   raw.get("details", {}).get("yCoord") is not None for raw in events),
            limitation="Available NHL plays only; historical types/coordinates can be absent")
        for raw in events:
            details = raw.get("details", {})
            ids = tuple(positive_id(details[field]) for field in PLAYER_FIELDS
                        if details.get(field) is not None)
            yield feed_record(ctx, "game_events", {"game_id": game.game_id, "raw": raw},
                source="nhl", key=f"{game.nhl_game_id}/{raw['eventId']}", raw=raw, report=report, player_ids=ids)


def collect_details(ctx, cursor):
    yield from cached_batches(ctx, lambda: detail_records(ctx), cursor, partition="nhl-game-details")


def normalize_details(item, ctx):
    row, raw = item.payload, item.payload["raw"]
    if item.dataset == "game_stats":
        result = {key: row[key] for key in ("game_id", "team_id", "entity_type")}
        result["entity_id"] = nhl_identity(ctx, "player", raw["playerId"]) if row["entity_type"] == "player" else row["team_id"]
        result.update({field: number(raw.get(source), count=True) for field, source in
                       (("goals", "goals" if row["entity_type"] == "player" else "score"),
                        ("assists", "assists"), ("shots", "sog"), ("saves", "saves"), ("shots_against", "shotsAgainst"))})
        result["time_on_ice"] = seconds(raw.get("toi"))
        if result["saves"] is not None and result["shots_against"] is not None and result["saves"] > result["shots_against"]:
            raise ValueError("Goalie saves exceed shots against")
        return result
    details = raw.get("details", {})
    player = next((details[field] for field in PLAYER_FIELDS[:6]
                   if details.get(field) is not None), None)
    x, y = number(details.get("xCoord")), number(details.get("yCoord"))
    if (x is None) != (y is None) or (x is not None and (abs(x) > 100 or abs(y) > 42.5)):
        raise ValueError("Invalid NHL rink coordinates")
    return {"game_id": row["game_id"], "event_id": str(positive_id(raw["eventId"])), "source": "nhl",
            "event_type": raw["typeDescKey"], "period": positive_id(raw["periodDescriptor"]["number"]),
            "time_in_period": seconds(raw["timeInPeriod"]), "order": number(raw["sortOrder"], count=True, required=True),
            "player_id": nhl_identity(ctx, "player", player) if player is not None else None,
            "team_id": nhl_identity(ctx, "team", details["eventOwnerTeamId"]) if details.get("eventOwnerTeamId") is not None else None,
            "x": x, "y": y, "coordinate_system": "nhl-rink-feet" if x is not None else None}


def operations():
    return {"game_schedule": JobOperation(collect_schedule, normalize_schedule, ready=team_scope_ready),
            "game_details": JobOperation(collect_details, normalize_details, ready=lambda ctx: bool(scoped_games(ctx)))}

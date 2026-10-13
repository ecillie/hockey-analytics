"""Published MoneyPuck downloads, native NHL IDs, and explicit source meanings."""
from dataclasses import dataclass
from io import BytesIO, TextIOWrapper
import csv
import re
from zipfile import ZipFile, BadZipFile

from app.jobs.shared.execution import JobOperation
from app.jobs.shared.identity import UnresolvedIdentity
from .common import batches, nhl_identity, positive_id, scan, team_scope_ready
from .feed_support import coverage, feed_record, number, stream_batches, unique_rows
from .games import scoped_games

BASE = "https://moneypuck.com/moneypuck/playerData/seasonSummary"
SHOTS = "https://peter-tanner.com/moneypuck/downloads"
KINDS = {"skaters": "moneypuck_skater_stats", "goalies": "moneypuck_goalie_stats",
         "teams": "moneypuck_team_stats", "lines": "moneypuck_line_stats"}
SITUATIONS = {"all", "5on5", "5on4", "4on5", "other"}
ALIASES = {"N.J": "NJD", "L.A": "LAK", "S.J": "SJS", "T.B": "TBL"}


@dataclass(frozen=True)
class DownloadPolicy:
    max_uncompressed_bytes: int = 512_000_000
    max_rows: int = 300000

    def __post_init__(self):
        if type(self.max_uncompressed_bytes) is not int or not 1 <= self.max_uncompressed_bytes <= 1_000_000_000:
            raise ValueError("Archive byte limit must be bounded")
        if type(self.max_rows) is not int or not 1 <= self.max_rows <= 1_000_000:
            raise ValueError("CSV row limit must be bounded")


def csv_rows(body, required, *, policy=DownloadPolicy(), archive=False):
    """Reiterable feed factory. ZIP is streamed, never extracted to disk."""
    def rows():
        zipped = None
        try:
            if archive:
                zipped = ZipFile(BytesIO(body))
                members = zipped.infolist()
                if (len(members) != 1 or members[0].is_dir() or not members[0].filename.endswith(".csv")
                        or members[0].flag_bits & 1 or members[0].file_size > policy.max_uncompressed_bytes):
                    raise ValueError("Shot archive must contain one bounded unencrypted CSV")
                stream = zipped.open(members[0])
            else:
                if len(body) > policy.max_uncompressed_bytes:
                    raise ValueError("CSV exceeds decompressed byte limit")
                stream = BytesIO(body)
            with TextIOWrapper(stream, encoding="utf-8-sig", newline="") as text:
                reader = csv.reader(text, strict=True)
                fields = next(reader, None)
                # Published team CSVs can repeat the team column. Preserve and
                # compare that known redundancy rather than letting DictReader
                # silently overwrite the first value. Other duplicates fail.
                if fields and fields.count("team") == 2:
                    fields[fields.index("team", fields.index("team") + 1)] = "team_source_duplicate"
                if (not fields or len(fields) != len(set(fields)) or not set(required) <= set(fields)):
                    raise ValueError("MoneyPuck CSV lacks distinct required headers")
                for index, values in enumerate(reader, 1):
                    if index > policy.max_rows:
                        raise ValueError("MoneyPuck CSV exceeds row limit")
                    if len(values) != len(fields):
                        raise ValueError("MoneyPuck CSV has a truncated/oversized row")
                    row = dict(zip(fields, values))
                    for redundant in ("team_source_duplicate", "team.1"):
                        if redundant in row and row[redundant] != row["team"]:
                            raise ValueError("MoneyPuck redundant team columns disagree")
                    yield row
        except (BadZipFile, UnicodeError, csv.Error) as exc:
            raise ValueError("Invalid MoneyPuck CSV/archive") from exc
        finally:
            if zipped is not None:
                zipped.close()
    return rows


def download(ctx, url):
    if ctx.client is None:
        raise ValueError("MoneyPuck requires a configured SourceClient")
    return ctx.client.get("moneypuck", url)


def line_ids(raw):
    value = raw["lineId"].strip()
    if not re.fullmatch(r"\d{14}|\d{21}", value):
        raise ValueError("MoneyPuck line ID must concatenate two/three seven-digit NHL IDs")
    ids = tuple(positive_id(value[index:index+7]) for index in range(0, len(value), 7))
    if len(ids) != len(set(ids)):
        raise ValueError("Repeated MoneyPuck line member")
    return ids


def team_identity(ctx, abbreviation, year):
    abbreviation = ALIASES.get(abbreviation, abbreviation)
    matches = [team.team_id for team in scan(ctx, "team_seasons", season=year)
               if team.abbreviation == abbreviation]
    if len(matches) != 1:
        raise UnresolvedIdentity(f"Unresolved MoneyPuck team abbreviation {abbreviation} in {year}")
    return matches[0]


def collect_stats(ctx, cursor, policy=DownloadPolicy()):
    items = []
    for year in range(ctx.config.first_season, ctx.config.last_season + 1):
        for game_type in ctx.config.game_types:
            for kind, dataset in KINDS.items():
                stage = "regular" if game_type == 2 else "playoffs"
                id_field = "lineId" if kind == "lines" else "playerId" if kind in ("skaters", "goalies") else "team"
                required = ("season", "team", "situation", "iceTime" if kind == "teams" else "icetime", id_field)
                required += ("I_F_xGoals",) if kind == "skaters" else ("xGoals",) if kind == "goalies" else ("xGoalsFor", "xGoalsAgainst")
                factory = csv_rows(download(ctx, f"{BASE}/{year}/{stage}/{kind}.csv"), required, policy=policy)
                rows = unique_rows(factory(), lambda row: (row[id_field], row["team"], row["situation"]))
                report = coverage(ctx, dataset, season=year, game_type=game_type, enumerated=len(rows),
                    limitation="Published CSV enumeration; independent population audit still required",
                    situations=sorted({row["situation"] for row in rows}))
                for raw in rows:
                    if number(raw["season"], count=True, required=True) != year or raw["situation"] not in SITUATIONS:
                        raise ValueError("MoneyPuck statistics season/situation differs from requested feed")
                    if raw.get("gameType") is not None and number(raw["gameType"], count=True) != game_type:
                        raise ValueError("MoneyPuck row differs from feed game type")
                    ids = line_ids(raw) if kind == "lines" else (positive_id(raw["playerId"]),) if kind in ("skaters", "goalies") else ()
                    payload = {"raw": raw, "kind": kind, "season": year, "game_type": game_type}
                    items.append(feed_record(ctx, dataset, payload, source="moneypuck",
                        key=f"{year}/{game_type}/{raw[id_field]}/{raw['team']}/{raw['situation']}",
                        raw=raw, report=report, player_ids=ids))
    yield from batches(ctx, items, cursor, partition="moneypuck-statistics")


def normalize_stats(item, ctx):
    row, raw = item.payload, item.payload["raw"]
    kind = row["kind"]
    result = {"source": "moneypuck", "season": row["season"], "game_type": row["game_type"],
              "situation": raw["situation"], "ice_time": number(raw["iceTime" if kind == "teams" else "icetime"], required=True)}
    aggregate = raw["team"] in ("TOT", "ALL", "all")
    if kind in ("skaters", "goalies"):
        result.update(player_id=nhl_identity(ctx, "player", raw["playerId"]),
                      team_scope="TOTAL" if aggregate else "TEAM",
                      team_id=None if aggregate else team_identity(ctx, raw["team"], row["season"]))
    else:
        result["team_id"] = team_identity(ctx, raw["team"], row["season"])
        result["expected_goals_for"] = number(raw["xGoalsFor"], required=True)
        result["expected_goals_against"] = number(raw["xGoalsAgainst"], required=True)
        if kind == "lines":
            result["player_ids"] = tuple(nhl_identity(ctx, "player", value) for value in line_ids(raw))
    if kind == "goalies":
        result["expected_goals_against"] = number(raw["xGoals"], required=True)
        result["goals_against"] = number(raw.get("goals"), count=True)
    if kind == "skaters":
        fields = {"expected_goals": "I_F_xGoals", "on_ice_expected_goals": "OnIce_F_xGoals",
                  "on_ice_expected_goals_pct": "onIce_xGoalsPercentage", "game_score": "gameScore"}
        result.update({field: number(raw.get(source), required=field == "expected_goals") for field, source in fields.items()})
        counts = {"shifts": "shifts", "individual_points": "I_F_points", "individual_goals": "I_F_goals",
                  "individual_primary_assists": "I_F_primaryAssists", "individual_secondary_assists": "I_F_secondaryAssists",
                  "individual_shots_on_goal": "I_F_shotsOnGoal", "individual_unblocked_attempts": "I_F_unblockedShotAttempts",
                  "takeaways": "I_F_takeaways", "giveaways": "I_F_giveaways", "shots_blocked": "shotsBlockedByPlayer",
                  "penalties": "penalties", "penalties_drawn": "penaltiesDrawn", "offensive_zone_shift_starts": "I_F_oZoneShiftStarts",
                  "defensive_zone_shift_starts": "I_F_dZoneShiftStarts", "neutral_zone_shift_starts": "I_F_neutralZoneShiftStarts"}
        result.update({field: number(raw.get(source), count=True) for field, source in counts.items()})
        values = [result[field] for field in ("individual_goals", "individual_primary_assists", "individual_secondary_assists", "individual_points")]
        if all(value is not None for value in values) and sum(values[:3]) != values[3]:
            raise ValueError("MoneyPuck points differ from goals plus primary/secondary assists")
        if (result["individual_shots_on_goal"] is not None and result["individual_goals"] is not None
                and result["individual_goals"] > result["individual_shots_on_goal"]):
            raise ValueError("MoneyPuck goals exceed shots on goal")
    return result


def shot_game_id(raw, year):
    value = positive_id(raw["game_id"])
    # Published archive game_id omits the four-digit season start year.
    result = value if value >= 1_000_000_000 else year * 1_000_000 + value
    if result // 1_000_000 != year:
        raise ValueError("Shot game ID differs from source season")
    return result


def shot_type(raw, year):
    return shot_game_id(raw, year) // 10000 % 100


def collect_shots(ctx, cursor, policy=DownloadPolicy()):
    tables, reports = {}, {}
    for year in range(ctx.config.first_season, ctx.config.last_season + 1):
        required = ("shotID", "game_id", "season", "event", "team", "shooterPlayerId")
        factory = csv_rows(download(ctx, f"{SHOTS}/shots_{year}.zip"), required, policy=policy, archive=True)
        counts, seen = {kind: 0 for kind in ctx.config.game_types}, set()
        for raw in factory():
            if number(raw["season"], count=True, required=True) != year:
                raise ValueError("Shot archive row differs from requested season")
            kind = shot_type(raw, year)
            if kind not in ctx.config.game_types:
                continue
            key = (shot_game_id(raw, year), positive_id(raw["shotID"]))
            if key in seen:
                raise ValueError("Duplicate MoneyPuck shot identity")
            seen.add(key)
            counts[kind] += 1
        tables[year] = factory
        for prior in scan(ctx, "shots", season=year):
            if prior.source != "moneypuck" or prior.game_type not in ctx.config.game_types:
                continue
            game = ctx.lookup("games", (prior.game_id,))
            if game is None or (game.nhl_game_id, positive_id(prior.shot_id)) not in seen:
                raise ValueError("MoneyPuck removed an accepted shot; review required because the contract has no tombstones")
        for kind in ctx.config.game_types:
            reports[year, kind] = coverage(ctx, "shots", season=year, game_type=kind,
                enumerated=counts[kind], status="limited", limitation="Goals, saves and misses; blocked attempts excluded")
    def records():
        for year, factory in tables.items():
            for raw in factory():
                kind = shot_type(raw, year)
                if kind not in ctx.config.game_types:
                    continue
                shooter = number(raw.get("shooterPlayerId"), count=True)
                ids = (shooter,) if shooter else ()
                payload = {"raw": raw, "season": year, "game_type": kind, "nhl_game_id": shot_game_id(raw, year)}
                yield feed_record(ctx, "shots", payload, source="moneypuck",
                    key=f"{payload['nhl_game_id']}/{raw['shotID']}", raw=raw, report=reports[year, kind], player_ids=ids)
    yield from stream_batches(ctx, records, cursor, partition="moneypuck-shots")


def normalize_shot(item, ctx):
    row, raw = item.payload, item.payload["raw"]
    game = ctx.find_unique("games", ("nhl_game_id",), (row["nhl_game_id"],))
    if game is None:
        raise UnresolvedIdentity(f"Missing NHL game {row['nhl_game_id']}; refresh schedules first")
    if game.status != "FINAL":
        raise ValueError("Shots require an accepted completed game")
    outcome = {"GOAL": "GOAL", "SHOT": "SAVE", "MISS": "MISS"}.get(raw["event"])
    if outcome is None:
        raise ValueError("Unsupported MoneyPuck shot outcome; blocked attempts are excluded")
    if raw.get("goal") not in (None, "") and number(raw["goal"], count=True) != int(outcome == "GOAL"):
        raise ValueError("Shot goal flag differs from event outcome")
    # Keep arena-adjusted and raw coordinates distinct; never combine axes.
    pair = ("arenaAdjustedXCord", "arenaAdjustedYCord") if any(raw.get(k) not in (None, "") for k in ("arenaAdjustedXCord", "arenaAdjustedYCord")) else ("xCord", "yCord")
    x, y = (number(raw.get(field)) for field in pair)
    if (x is None) != (y is None) or (x is not None and (abs(x) > 100 or abs(y) > 42.5)):
        raise ValueError("Invalid MoneyPuck coordinate pair")
    shooter = number(raw.get("shooterPlayerId"), count=True)
    return {"source": "moneypuck", "shot_id": str(positive_id(raw["shotID"])), "game_id": game.game_id,
            "season": row["season"], "game_type": row["game_type"], "outcome": outcome,
            "player_id": nhl_identity(ctx, "player", shooter) if shooter else None,
            "team_id": team_identity(ctx, raw["team"], row["season"]), "x": x, "y": y,
            "coordinate_system": ("moneypuck-arena-adjusted-feet" if pair[0].startswith("arena") else "moneypuck-rink-feet") if x is not None else None,
            "expected_goals": number(raw.get("xGoal"))}


def operations(policy=DownloadPolicy()):
    return {"moneypuck_stats": JobOperation(lambda ctx, cursor: collect_stats(ctx, cursor, policy), normalize_stats, ready=team_scope_ready),
            "moneypuck_shots": JobOperation(lambda ctx, cursor: collect_shots(ctx, cursor, policy), normalize_shot,
                                          ready=lambda ctx: team_scope_ready(ctx) and bool(scoped_games(ctx)))}

"""Dated NHL EDGE observations with conservative metric and feed coverage."""
from dataclasses import dataclass
from app.jobs.shared.execution import JobOperation
from app.jobs.shared.identity import UnresolvedIdentity
from app.jobs.shared.source_requests import SourceHTTPError
from .common import batches, nhl_identity, positive_id, team_scope_ready
from .feed_support import coverage, feed_record, number, unique_rows
from .nhl import WEB, json_get, season_id, season_year, summaries


@dataclass(frozen=True)
class EdgePolicy:
    collect_teams: bool = True
    collect_skaters: bool = True
    collect_goalies: bool = True

    def __post_init__(self):
        if any(type(value) is not bool for value in (self.collect_teams, self.collect_skaters, self.collect_goalies)):
            raise ValueError("EDGE feed switches must be booleans")
        if not all((self.collect_teams, self.collect_skaters, self.collect_goalies)):
            raise ValueError("Required EDGE summary entity families cannot be disabled")


@dataclass(frozen=True)
class MetricField:
    path: tuple[str, ...]
    unit: str
    definition: str

    def __post_init__(self):
        if not self.path or not all(isinstance(key, str) and key for key in self.path) or not self.definition.strip():
            raise ValueError("Sample metrics require explicit source paths and definitions")
        if self.unit not in ("mph", "km/h", "miles", "km", "feet", "seconds", "ratio", "count"):
            raise ValueError("Unsupported sample metric unit")


@dataclass(frozen=True)
class SampleFeed:
    """Infrastructure-supplied audited source paths; every feed is a limited sample."""
    dataset: str
    entity_type: str
    nhl_id: int
    url_template: str
    records_path: tuple[str, ...]
    measurements: tuple[MetricField, ...]
    game_id_field: str = "gameId"
    event_id_field: str = "eventId"

    def __post_init__(self):
        if self.dataset not in ("edge_games", "edge_events") or self.entity_type not in ("player", "team"):
            raise ValueError("Samples require a supported EDGE family/entity")
        positive_id(self.nhl_id)
        if (not self.url_template.startswith(f"{WEB}/edge/") or not self.records_path
                or not self.measurements or len({field.path for field in self.measurements}) != len(self.measurements)):
            raise ValueError("Sample feeds require an NHL EDGE URL and distinct audited metric paths")
        self.url_template.format(nhl_id=self.nhl_id, season=20212022, game_type=2)


def at_path(value, path):
    for key in path:
        value = value[key]
    return value


def collect_samples(ctx, year, game_type, feeds):
    items, configured = [], set()
    for feed in feeds:
        configured.add(feed.dataset)
        url = feed.url_template.format(nhl_id=feed.nhl_id, season=season_id(year), game_type=game_type)
        try:
            data = json_get(ctx, url)
        except SourceHTTPError as exc:
            if exc.status != 404:
                raise
            coverage(ctx, feed.dataset, season=year, game_type=game_type, status="unavailable",
                     limitation="Optional configured sample feed returned HTTP 404")
            continue
        identity_field = "teamId" if feed.entity_type == "team" else "playerId"
        if (positive_id(data[identity_field]) != feed.nhl_id or season_year(data["season"]) != year
                or data["gameType"] != game_type):
            raise ValueError("EDGE sample feed differs from requested entity/season/type")
        rows = at_path(data, feed.records_path)
        if not isinstance(rows, list):
            raise ValueError("EDGE sample lacks explicit record list")
        identity_field = feed.game_id_field if feed.dataset == "edge_games" else feed.event_id_field
        rows = unique_rows(rows, lambda row: str(positive_id(row[identity_field])))
        report = coverage(ctx, feed.dataset, season=year, game_type=game_type, enumerated=len(rows),
                          status="limited", limitation="Configured recent-game/selected-event sample; never complete history")
        for raw in rows:
            metrics = {}
            for field in feed.measurements:
                value = number(at_path(raw, field.path), count=field.unit == "count", required=True)
                if value < 0 or (field.unit == "ratio" and value > 1):
                    raise ValueError("Invalid EDGE sample measurement")
                metrics[".".join(field.path)] = {"value": value, "unit": field.unit, "definition": field.definition}
            payload = {"entity_type": feed.entity_type, "nhl_id": feed.nhl_id, "season": year,
                       "game_type": game_type, "metrics": metrics, "observed_at": ctx.run.started_at}
            nhl_game = raw.get(feed.game_id_field)
            if nhl_game is not None:
                game = ctx.find_unique("games", ("nhl_game_id",), (positive_id(nhl_game),))
                if game is None:
                    raise UnresolvedIdentity(f"Missing NHL EDGE sample game {nhl_game}; load schedules first")
                if game.season != year or game.game_type != game_type:
                    raise ValueError("EDGE sample game differs from requested season/type")
                payload["game_id"] = game.game_id
            elif feed.dataset == "edge_games":
                raise ValueError("EDGE game sample lacks a game identity")
            if feed.dataset == "edge_events":
                payload["event_id"] = str(positive_id(raw[feed.event_id_field]))
            items.append(feed_record(ctx, feed.dataset, payload, source="nhl-edge",
                key=f"{feed.entity_type}/{feed.nhl_id}/{year}/{game_type}/{raw[identity_field]}", raw=raw, report=report,
                player_ids=(feed.nhl_id,) if feed.entity_type == "player" else ()))
    for dataset in {"edge_games", "edge_events"} - configured:
        coverage(ctx, dataset, season=year, game_type=game_type, status="unavailable",
            limitation="No independently enumerated feed configured; recent games/top events are limited samples")
    return items


# Only source-labelled measurements are normalized. Unknown numeric fields are
# retained in provenance and reported, never guessed from magnitude or position.
COUNT_FIELDS = {"burstsOver22", "bursts20To22", "bursts18To20", "speedBurstsOver22",
                "speedBursts20To22", "speedBursts18To20", "shotsOnGoal", "goals", "saves",
                "shotsAgainst", "goalsAgainst", "gamesPlayed"}
RATIO_FIELDS = {"shootingPctg", "savePctg", "offensiveZonePctg", "defensiveZonePctg", "neutralZonePctg"}
SECTIONS = {"skatingSpeed": "speed", "shotSpeed": "speed", "skatingDistance": "distance",
            "shotLocation": "counts", "zoneTime": "ratio", "savePercentage": "ratio"}


def parse_metrics(raw):
    metrics, breakdowns, unknown = {}, {}, []
    def visit(value, path, category):
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, (*path, key), category)
            return
        if isinstance(value, list):
            # Lists can be selected events or limited recent-game samples. They
            # are handled separately, never flattened into exhaustive history.
            return
        if value is None or isinstance(value, (bool, str)):
            return
        name = path[-1]
        unit = None
        if name in ("imperial", "metric") and category in ("speed", "distance"):
            unit = ("mph" if name == "imperial" else "km/h") if category == "speed" else ("miles" if name == "imperial" else "km")
        elif name in COUNT_FIELDS:
            unit = "count"
        elif name in RATIO_FIELDS:
            unit = "ratio"
        if unit is None:
            unknown.append(".".join(path))
            return
        value = number(value, count=unit == "count", required=True)
        if value < 0 or (unit == "ratio" and value > 1):
            raise ValueError("Invalid EDGE nonnegative measurement/ratio")
        key = ".".join(path)
        measurement = {"value": value, "unit": unit, "definition": f"NHL EDGE source field {key}"}
        if len(path) > 2 and category in ("counts", "ratio"):
            breakdowns.setdefault(".".join(path[:-1]), {})[name] = measurement
        metrics[key] = measurement
    for section, category in SECTIONS.items():
        if section in raw:
            visit(raw[section], (section,), category)
    if not metrics:
        raise ValueError("EDGE response has no recognized source-labelled measurements")
    return metrics, breakdowns or None, sorted(unknown)


def collect(ctx, cursor, policy=EdgePolicy(), sample_feeds=()):
    items = []
    for year in range(ctx.config.first_season, ctx.config.last_season + 1):
        for game_type in ctx.config.game_types:
            population = []
            for kind, entity, field in (("team", "team", "teamId"), ("skater", "player", "playerId"), ("goalie", "player", "playerId")):
                population.extend((kind, entity, positive_id(row[field])) for row in summaries(ctx, kind, year, game_type))
            coverage(ctx, "edge_summaries", season=year, game_type=game_type,
                     enumerated=len(population), expected=len(population),
                     limitation="Eligibility from NHL participation; each entity requires a published detail response")
            for kind, entity, nhl_id in population:
                endpoint = "team" if entity == "team" else kind
                try:
                    raw = json_get(ctx, f"{WEB}/edge/{endpoint}-detail/{nhl_id}/{season_id(year)}/{game_type}")
                except SourceHTTPError as exc:
                    if exc.status == 404:
                        coverage(ctx, "edge_summaries", season=year, game_type=game_type, status="unavailable",
                                 entity_type=entity, nhl_id=nhl_id, limitation="Required entity detail returned HTTP 404")
                    raise
                field = "teamId" if entity == "team" else "playerId"
                if positive_id(raw[field]) != nhl_id:
                    raise ValueError("EDGE returned a different entity")
                if "season" in raw and season_year(raw["season"]) != year:
                    raise ValueError("EDGE returned a different season")
                if "gameType" in raw and raw["gameType"] != game_type:
                    raise ValueError("EDGE returned a different game type")
                available = raw.get("seasonsWithEdgeStats")
                if available is not None:
                    if not isinstance(available, list):
                        raise ValueError("Malformed EDGE eligibility manifest")
                    supported = any(season_year(row["season"]) == year and game_type in row["gameTypes"] for row in available)
                    if not supported:
                        coverage(ctx, "edge_summaries", season=year, game_type=game_type, status="unavailable",
                                 entity_type=entity, nhl_id=nhl_id, limitation="Requested scope absent from EDGE eligibility manifest")
                        raise ValueError("Required EDGE summary is unavailable for an eligible NHL participant")
                metrics, breakdowns, unknown = parse_metrics(raw)
                report = coverage(ctx, "edge_summaries", season=year, game_type=game_type, enumerated=1, status="limited",
                                  entity_type=entity, nhl_id=nhl_id, unknown_measurements=unknown,
                                  limitation="Dated source summary; unknown fields retained in raw provenance")
                payload = {"nhl_id": nhl_id, "entity_type": entity, "season": year, "game_type": game_type,
                           "metrics": metrics, "breakdowns": breakdowns, "observed_at": ctx.run.started_at}
                items.append(feed_record(ctx, "edge_summaries", payload, source="nhl-edge",
                    key=f"{entity}/{nhl_id}/{year}/{game_type}", raw=raw, report=report,
                    player_ids=(nhl_id,) if entity == "player" else ()))
            items.extend(collect_samples(ctx, year, game_type, sample_feeds))
    yield from batches(ctx, items, cursor, partition="nhl-edge")


def normalize(item, ctx):
    result = dict(item.payload)
    result["entity_id"] = nhl_identity(ctx, result["entity_type"], result.pop("nhl_id"))
    return result


def operation(policy=EdgePolicy(), sample_feeds=()):
    return JobOperation(lambda ctx, cursor: collect(ctx, cursor, policy, sample_feeds), normalize, ready=team_scope_ready)

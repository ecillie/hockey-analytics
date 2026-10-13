"""Current/recent USA Today transactions; no archive or historical season queries."""
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
import json

from app.jobs.shared.data_contracts import canonical_json
from app.jobs.shared.execution import JobOperation
from app.jobs.shared.identity import UnresolvedIdentity
from app.jobs.shared.normalization import iso_date, utc_timestamp
from app.jobs.shared.validation import CollectionBatch
from .common import scan, source_record
from .html import Document

URL = "https://sportsdata.usatoday.com/hockey/nhl/transactions"
SOURCE = "usatoday"
EVENT_TYPES = {
    "Signed": "SIGNING", "Signed as Free Agent": "SIGNING", "Contract extended": "EXTENSION",
    "Contract Extension": "EXTENSION", "Traded": "TRADE", "Waived": "WAIVED",
    "Placed on long-term injured reserve": "LTIR", "Activated from injured reserve": "ACTIVATED",
    "Activated from long-term injured reserve": "ACTIVATED", "Placed on injured reserve": "IR",
    "Called up from minors": "RECALLED", "Sent to minors": "ASSIGNED", "Suspended": "SUSPENDED",
    "Suspension Over": "SUSPENSION_OVER",
}


@dataclass(frozen=True)
class TransactionPolicy:
    recent_days: int = 3
    maximum_recent_days: int = 31

    def __post_init__(self):
        if (type(self.recent_days) is not int or type(self.maximum_recent_days) is not int
                or not 1 <= self.recent_days <= self.maximum_recent_days <= 31):
            raise ValueError("Transactions require a bounded current/recent window (1–31 days)")


def parse_page(body):
    try:
        page = Document(body).next_data()["props"]["pageProps"]["fallback"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Changed USA Today page structure") from exc
    rows, cursor = page.get("transactions"), page.get("cursor", ...)
    if (not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
            or cursor is ... or (cursor is not None and not isinstance(cursor, str))
            or type(page.get("numResults")) is not int or page["numResults"] < len(rows)):
        raise ValueError("Changed/incomplete USA Today transaction enumeration")
    if not rows and page["numResults"] != 0:
        raise ValueError("USA Today returned an unverified empty population")
    return rows, cursor


def event_date(row):
    return iso_date(row["date"]["full"])


def participants(row):
    players = row.get("players")
    if players is None:
        players = [row["player"]]
    if not isinstance(players, list) or not players or any(not isinstance(player, dict) for player in players):
        raise ValueError("Transaction has no explicit participant enumeration")
    return players


def event_type(row):
    name = row["transactionType"]["name"].strip()
    if not name:
        raise ValueError("Transaction has no event type")
    return EVENT_TYPES.get(name, name)


def recent_rows(ctx, policy):
    days = max(policy.recent_days, ctx.config.correction_lookback_days)
    if days > policy.maximum_recent_days:
        raise ValueError("Transaction correction lookback exceeds current/recent policy")
    if ctx.client is None:
        raise ValueError("Transactions require a configured SourceClient")
    today = ctx.run.started_at.date()
    lower = today - timedelta(days=days)
    rows, cursor = parse_page(ctx.client.get(SOURCE, URL).decode("utf-8"))
    if cursor:
        frontier = json.loads(cursor)
        if (not isinstance(frontier, list) or len(frontier) != 2 or not rows
                or frontier != [rows[-1]["date"]["full"], rows[-1]["id"]]
                or event_date(rows[-1]) != min(event_date(row) for row in rows)):
            raise ValueError("Unverifiable USA Today recent-window frontier")
        # A same-date boundary can omit other events that day. Never call it complete.
        if iso_date(frontier[0]) >= lower:
            raise ValueError("USA Today page truncates the requested recent window; narrow the window or supply verified pagination")
    selected = {}
    for row in rows:
        if row["league"]["abbreviation"] != "NHL":
            raise ValueError("Transaction feed contains another league")
        day = event_date(row)
        if day is None or day > today:
            raise ValueError("Transaction event date is missing/in the future")
        if day < lower:
            continue
        source_id = row["id"]
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("Transaction requires a durable source event ID")
        previous = selected.get(source_id)
        if previous is not None and previous != row:
            # A source-provided correction time orders duplicate revisions; fetch order does not.
            old_time, new_time = previous.get("updatedAt"), row.get("updatedAt")
            if not old_time or not new_time or utc_timestamp(old_time) == utc_timestamp(new_time):
                raise ValueError("Conflicting duplicate transaction revisions need review")
            if utc_timestamp(old_time) > utc_timestamp(new_time):
                continue
        selected[source_id] = row
    return [selected[key] for key in sorted(selected)], {"window_start": lower.isoformat(), "window_end": today.isoformat()}


def collect(ctx, cursor, policy=TransactionPolicy()):
    rows, scope = recent_rows(ctx, policy)
    groups = []
    for row in rows:
        updated_at = utc_timestamp(row.get("updatedAt"))
        group = [source_record(ctx, "transactions", row, source=SOURCE, key=row["id"], raw=row,
                               scope={**scope, "record_key": [SOURCE, row["id"]]}, source_updated_at=updated_at)]
        if event_type(row) in ("SIGNING", "EXTENSION"):
            for player in participants(row):
                group.append(source_record(ctx, "refresh_requests", {"transaction": row, "player": player},
                    source=SOURCE, key=f"contracts/{row['id']}/{player['playerID']}", raw=row, scope=scope,
                    source_updated_at=updated_at))
        if len(group) > ctx.config.max_batch_records:
            raise ValueError("Transaction and all refresh requests must fit one atomic batch")
        groups.append(group)
    fingerprint = sha256(canonical_json([[row["id"], row] for row in rows])).hexdigest()
    offset = 0
    if cursor is not None:
        if (not isinstance(cursor, dict) or cursor.get("digest") != fingerprint
                or cursor.get("window") != scope or type(cursor.get("offset")) is not int
                or not 0 <= cursor["offset"] <= len(groups)):
            raise ValueError("Recent source enumeration changed; rerun without resume")
        offset = cursor["offset"]
    while True:
        end, items = offset, []
        while end < len(groups) and len(items) + len(groups[end]) <= ctx.config.max_batch_records:
            items.extend(groups[end])
            end += 1
        yield CollectionBatch(tuple(items), {"digest": fingerprint, "window": scope, "offset": end},
                              len(items), final=end == len(groups))
        if end == len(groups):
            return
        offset = end


def normalize(item, ctx):
    if item.dataset == "refresh_requests":
        row, player = item.payload["transaction"], item.payload["player"]
        player_id = ctx.resolve(SOURCE, "player", player["playerID"])
        digest = sha256(canonical_json(row)).hexdigest()
        request_id = sha256(canonical_json(["contracts", SOURCE, row["id"], digest, player_id])).hexdigest()
        previous = ctx.lookup("refresh_requests", (request_id,))
        return previous or {"request_id": request_id, "job": "contracts", "player_id": player_id,
            "cause_source": SOURCE, "cause_id": row["id"], "cause_digest": digest, "requested_at": ctx.run.started_at}
    row = item.payload
    result = {"source": SOURCE, "source_id": row["id"], "event_date": event_date(row),
              "event_type": event_type(row), "description": row.get("description") or None,
              "participants": tuple({"player_id": ctx.resolve(SOURCE, "player", player["playerID"]),
                                     "role": player.get("role")} for player in participants(row))}
    for field, source_field in (("to_team_id", "team"), ("from_team_id", "fromTeam")):
        team = row.get(source_field)
        if team and team.get("teamID"):
            result[field] = ctx.resolve(SOURCE, "team", team["teamID"])
    return result


def operation(policy=TransactionPolicy()):
    return JobOperation(lambda ctx, cursor: collect(ctx, cursor, policy), normalize,
        ready=lambda ctx: bool(scan(ctx, "player_profiles")) and bool(scan(ctx, "teams")))

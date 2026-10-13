"""Conservative current-state projection from accepted NHL evidence and overrides."""
from dataclasses import dataclass
from datetime import timedelta

from app.jobs.shared.execution import JobOperation
from .common import batches, evidence, scan, source_record


@dataclass(frozen=True)
class RosterPolicy:
    maximum_snapshot_age_days: int = 3

    def __post_init__(self):
        if type(self.maximum_snapshot_age_days) is not int or not 0 <= self.maximum_snapshot_age_days <= 31:
            raise ValueError("Roster freshness must be bounded to 0–31 days")


# Semantics are source event types, never inferred from free-text descriptions.
SUPPORTED = {"LTIR": "LTIR", "ACTIVATED": "ACTIVE", "RECALLED": "ACTIVE",
             "ASSIGNED": "MINORS", "TRADE": "ACTIVE"}
UNCERTAIN = {"IR", "SUSPENDED", "SUSPENSION_OVER", "WAIVED"}


def transition(event, player_id):
    team_id = event.to_team_id
    if event.event_type == "TRADE" and len(event.participants) > 1:
        participant = next(row for row in event.participants if row.player_id == player_id)
        if participant.role not in ("to_team", "from_team"):
            raise ValueError("Multi-participant trade lacks explicit participant team direction")
        team_id = event.to_team_id if participant.role == "to_team" else event.from_team_id
    return SUPPORTED.get(event.event_type), team_id


def derive(ctx, player_id, observations, transactions, overrides, policy):
    today = ctx.run.started_at.date()
    active = [row for row in overrides if row.player_id == player_id
              and row.effective_from <= today and (row.effective_to is None or today <= row.effective_to)]
    if len(active) > 1:
        raise ValueError("Overlapping roster overrides require review")
    if active:
        override = active[0]
        return {"player_id": player_id, "status": override.status, "team_id": override.team_id,
                "effective_date": today, "override_id": override.override_id}, [], override
    candidates = [row for row in observations if row.player_id == player_id and row.complete_scope
                  and row.source == "nhl" and ctx.run.started_at - timedelta(days=policy.maximum_snapshot_age_days) <= row.observed_at <= ctx.run.started_at]
    latest = max((row.observed_at for row in candidates), default=None)
    snapshots = [row for row in candidates if row.observed_at == latest]
    if len({row.team_id for row in snapshots}) > 1:
        raise ValueError("Conflicting same-time NHL roster teams require review")
    events = [row for row in transactions if row.event_date <= today
              and any(participant.player_id == player_id for participant in row.participants)
              and row.event_type not in ("SIGNING", "EXTENSION")]
    events.sort(key=lambda row: (row.event_date, row.source, row.source_id))
    state = {"player_id": player_id, "status": "ACTIVE", "team_id": snapshots[0].team_id,
             "effective_date": latest.date()} if snapshots else None
    support = list(snapshots)
    if events:
        last_date = events[-1].event_date
        last = [row for row in events if row.event_date == last_date]
        transitions = {transition(row, player_id) for row in last}
        if len(transitions) > 1:
            raise ValueError("Conflicting same-day transaction states have no trustworthy order")
        event = last[-1]
        if event.event_type in UNCERTAIN or event.event_type not in SUPPORTED:
            # A later complete snapshot can supply positive ACTIVE evidence for waivers.
            if not snapshots or event.event_date >= latest.date() or event.event_type in ("IR", "SUSPENDED"):
                raise ValueError(f"Unsupported/uncertain roster transition {event.event_type}; preserve last supported state")
        else:
            status, team_id = transition(event, player_id)
            if team_id is None:
                raise ValueError("Roster-changing transaction has no explicit NHL team")
            # Fetch time is not proof of injury activation or recall from an assignment.
            restrictive = status in ("LTIR", "MINORS")
            if restrictive or not snapshots or event.event_date >= latest.date():
                state = {"player_id": player_id, "status": status, "team_id": team_id,
                         "effective_date": event.event_date}
                support = last
    if state is None:
        raise ValueError("Missing fresh positive NHL roster evidence; absence cannot change status")
    lineage = []
    for row in support:
        dataset = "transactions" if hasattr(row, "event_date") else "roster_observations"
        ids = evidence(ctx, dataset, row)
        if not ids:
            raise ValueError("Roster evidence has no accepted source lineage")
        lineage.extend(ids)
    state["evidence"] = tuple(sorted(set(lineage), key=str))
    return state, support, None


def collect(ctx, cursor, policy=RosterPolicy()):
    observations = scan(ctx, "roster_observations")
    transactions = scan(ctx, "transactions")
    overrides = scan(ctx, "roster_overrides")
    # Include prior states/memberships so incomplete evidence is visible, never a silent deletion.
    players = {row.player_id for row in (*observations, *overrides, *scan(ctx, "roster_state"))}
    players.update(participant.player_id for event in transactions for participant in event.participants)
    players.update(row.player_id for row in scan(ctx, "memberships", season=ctx.config.current_season))
    items = []
    for player_id in sorted(players):
        raw = {"player_id": player_id,
               "rosters": [row.model_dump(mode="json") for row in observations if row.player_id == player_id],
               "transactions": [row.model_dump(mode="json") for row in transactions if any(participant.player_id == player_id for participant in row.participants)],
               "overrides": [row.model_dump(mode="json") for row in overrides if row.player_id == player_id]}
        try:
            state, _, override = derive(ctx, player_id, observations, transactions, overrides, policy)
            payload = {"record": state, "override": override}
        except ValueError as exc:
            payload = {"error": str(exc)}
        items.append(source_record(ctx, "roster_state", payload, source="roster_reconciliation",
                                   key=player_id, raw=raw))
    yield from batches(ctx, items, cursor, partition="roster-state")


def normalize(item, ctx):
    if "error" in item.payload:
        raise ValueError(item.payload["error"])
    result = dict(item.payload["record"])
    previous = ctx.lookup("roster_state", (result["player_id"],))
    if item.payload["override"] is not None:
        if previous and previous.override_id == result["override_id"] and (previous.status, previous.team_id) == (result["status"], result["team_id"]):
            return previous
        result["evidence"] = (item.observation.observation_id,)
    # Recompute from the complete accepted event set. Effective dates on a prior
    # projection cannot defeat accepted corrections or newly arrived LTIR evidence.
    return result


def operation(policy=RosterPolicy()):
    return JobOperation(lambda ctx, cursor: collect(ctx, cursor, policy), normalize,
        ready=lambda ctx: bool(scan(ctx, "memberships", season=ctx.config.current_season)) or bool(scan(ctx, "transactions")) or bool(scan(ctx, "roster_overrides")))

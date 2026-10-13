"""Source support: stable identities, retained payloads, and bounded enumeration."""
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from app.jobs.shared.access_contracts import ReadRequest
from app.jobs.shared.data_contracts import RECORD_DEFINITIONS, SourceObservation, canonical_json
from app.jobs.shared.identity import UnresolvedIdentity
from app.jobs.shared.normalization import integer
from app.jobs.shared.validation import CollectionBatch, SourceRecord

VERSION = "core-sources-1"


def stable_id(*parts):
    # Signed 63-bit surrogate; collisions are rejected by the acceptance boundary.
    return int.from_bytes(sha256(canonical_json(parts)).digest()[:8], "big") & ((1 << 63) - 1) or 1


def positive_id(value):
    result = integer(value)
    if result is None or result <= 0:
        raise ValueError("Missing/invalid durable source ID")
    return result


def localized(value):
    if isinstance(value, dict):
        value = value.get("default")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing source text")
    return value.strip()


def source_record(ctx, dataset, payload, *, source, key, raw=None, scope=None, source_updated_at=None):
    definition = RECORD_DEFINITIONS[dataset]
    json_payload = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    record_scope = {}
    if isinstance(json_payload, dict) and all(field in json_payload for field in definition.key_fields):
        record_scope = {"record_key": [json_payload[field] for field in definition.key_fields]}
    raw = json_payload if raw is None else raw
    digest = sha256(canonical_json(raw)).hexdigest()
    # A run is a new dated observation; a resumed batch in that run is stable.
    observation = SourceObservation(
        observation_id=uuid5(NAMESPACE_URL, f"{ctx.run.run_id}/{source}/{dataset}/{key}/{digest}"),
        source=source, source_key=str(key), dataset=dataset,
        observed_at=ctx.run.started_at, content_digest=digest,
        transformation_version=VERSION, scope={**ctx.config.scope, **record_scope, **(scope or {})},
        payload=raw, source_updated_at=source_updated_at)
    return SourceRecord(dataset, payload, observation)


def batches(ctx, items, cursor, *, partition="records"):
    """Resume only a frozen enumeration; never skip offsets in a changed response."""
    items = tuple(items)
    digest = sha256(canonical_json([
        [item.dataset, item.observation.source_key, item.observation.content_digest]
        for item in items])).hexdigest()
    offset = 0
    if cursor is not None:
        if (not isinstance(cursor, dict) or cursor.get("partition") != partition
                or cursor.get("digest") != digest or type(cursor.get("offset")) is not int
                or not 0 <= cursor["offset"] <= len(items)):
            raise ValueError("Source enumeration changed; rerun without resume")
        offset = cursor["offset"]
    while True:
        end = min(offset + ctx.config.max_batch_records, len(items))
        page = items[offset:end]
        yield CollectionBatch(page, {"partition": partition, "digest": digest, "offset": end},
                              len(page), final=end == len(items))
        if end == len(items):
            return
        offset = end


def scan(ctx, dataset_name, **filters):
    """Merge validation-only candidates over one paginated accepted snapshot."""
    rows, cursor, seen = {}, None, set()
    while True:
        page = ctx.reader.scan(ReadRequest(dataset=dataset_name, snapshot=ctx.snapshot,
            scope_json=canonical_json(filters), cursor=cursor))
        if page.snapshot != ctx.snapshot:
            raise ValueError("Read page changed its snapshot")
        for row in page.records:
            rows[row.write.key] = row.write.decoded()
        cursor = page.next_cursor
        if cursor is None:
            break
        if cursor in seen:
            raise ValueError("Read cursor repeated")
        seen.add(cursor)
    for (name, key), record in ctx.overlay.items():
        if name == dataset_name:
            if all(record.model_dump(mode="json")[field] == value for field, value in filters.items()):
                rows[key] = record
            else:
                rows.pop(key, None)
    return tuple(rows[key] for key in sorted(rows, key=repr))


def nhl_identity(ctx, entity, source_id):
    """NHL numeric IDs establish identity; canonical IDs can differ from them."""
    source_id = positive_id(source_id)
    target, field = {"player": ("player_profiles", "nhl_player_id"),
                     "team": ("teams", "nhl_team_id")}[entity]
    existing = ctx.find_unique(target, (field,), (source_id,))
    if existing is None:
        raise UnresolvedIdentity(f"Missing NHL {entity} {source_id}; run reference/profile discovery")
    return getattr(existing, f"{entity}_id")


def season_ready(ctx):
    return all(ctx.lookup("seasons", (season,)) is not None
               for season in range(ctx.config.first_season, ctx.config.last_season + 1))


def team_scope_ready(ctx):
    return season_ready(ctx) and all(scan(ctx, "team_seasons", season=season)
        for season in range(ctx.config.first_season, ctx.config.last_season + 1))


def evidence(ctx, dataset, record):
    key = RECORD_DEFINITIONS[dataset].key(record)
    stored = ctx.reader.get(dataset, key, snapshot=ctx.snapshot)
    if (dataset, key) not in ctx.overlay and stored is not None:
        return stored.write.observation_ids
    # Candidates created by preceding validation-only jobs have no stored writes.
    return tuple(obs.observation_id for obs in scan(ctx, "source_observations", dataset=dataset)
                 if obs.scope.get("record_key") == list(RECORD_DEFINITIONS[dataset].json_key(record)))

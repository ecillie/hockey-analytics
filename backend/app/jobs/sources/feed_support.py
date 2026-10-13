"""Feed enumeration evidence and exact source numeric conversions."""
from decimal import Decimal, InvalidOperation
import math

from .common import source_record
from app.jobs.shared.data_contracts import canonical_json


def number(value, *, count=False, required=False):
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError("Required source measurement is missing")
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not a source measurement")
    try:
        value = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid source measurement") from exc
    if not value.is_finite():
        raise ValueError("Source measurements must be finite")
    if count:
        if value < 0 or value != value.to_integral_value():
            raise ValueError("Source count must be a nonnegative exact integer")
        return int(value)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Source measurement is out of range")
    return result


def coverage(ctx, dataset, *, season=None, game_type=None, game_id=None,
             enumerated=0, expected=None, status="available", limitation=None, **details):
    """Counts describe source enumeration, never accepted database population."""
    entry = {"dataset": dataset, "season": season, "game_type": game_type,
             "game_id": game_id, "status": status, "enumerated_records": enumerated,
             "expected_records": expected, "limitation": limitation, **details}
    ctx.source_coverage.append(entry)
    return entry


def unique_rows(rows, identity):
    """Repeated identical facts are harmless; conflicting duplicates require review."""
    result = {}
    for row in rows:
        key = identity(row)
        if key in result and canonical_json(result[key]) != canonical_json(row):
            raise ValueError(f"Conflicting duplicate source identity: {key}")
        result[key] = row
    return tuple(result[key] for key in sorted(result, key=repr))


def feed_record(ctx, dataset, payload, *, source, key, raw, report, player_ids=()):
    return source_record(ctx, dataset, payload, source=source, key=key, raw=raw,
                         scope={"feed_coverage": report, "nhl_player_ids": list(player_ids)}, version="game-data-sources-1")


def missing_player_discovery(ctx):
    """Build the existing profile-job input from retained dependent observations.

    Only source adapters that explicitly declare NHL IDs may add these IDs.
    Reprocessing follows a separate successful player_profiles run.
    """
    from .common import positive_id
    from .nhl import Discovery
    from app.jobs.shared.access_contracts import ReadRequest
    ids, cursor, seen = set(), None, set()
    def include(observation):
        if observation.source in ("nhl", "moneypuck", "nhl-edge") and observation.transformation_version == "game-data-sources-1":
            ids.update(positive_id(value) for value in observation.scope.get("nhl_player_ids", ()))
    while True:
        page = ctx.reader.scan(ReadRequest(dataset="source_observations", snapshot=ctx.snapshot,
            scope_json=canonical_json({"transformation_version": "game-data-sources-1"}), cursor=cursor))
        if page.snapshot != ctx.snapshot:
            raise ValueError("Discovery page changed its snapshot")
        for row in page.records:
            include(row.write.decoded())
        cursor = page.next_cursor
        if cursor is None:
            break
        if cursor in seen:
            raise ValueError("Discovery cursor repeated")
        seen.add(cursor)
    for (dataset, _), observation in ctx.overlay.items():
        if dataset == "source_observations":
            include(observation)
    return Discovery(player_ids=tuple(sorted(value for value in ids
        if ctx.find_unique("player_profiles", ("nhl_player_id",), (value,)) is None)))


def stream_batches(ctx, factory, cursor, *, partition):
    """Two passes over one downloaded feed bound record memory and freeze resume."""
    from hashlib import sha256
    from app.jobs.shared.validation import CollectionBatch
    digest, total = sha256(), 0
    for item in factory():
        digest.update(canonical_json([item.dataset, item.observation.source_key, item.observation.content_digest]))
        total += 1
    fingerprint = digest.hexdigest()
    offset = 0
    if cursor is not None:
        if (not isinstance(cursor, dict) or cursor.get("partition") != partition
                or cursor.get("digest") != fingerprint or type(cursor.get("offset")) is not int
                or not 0 <= cursor["offset"] <= total):
            raise ValueError("Source enumeration changed; rerun without resume")
        offset = cursor["offset"]
    pending = []
    for index, item in enumerate(factory(), 1):
        if index <= offset:
            continue
        pending.append(item)
        if len(pending) == ctx.config.max_batch_records or index == total:
            yield CollectionBatch(tuple(pending), {"partition": partition, "digest": fingerprint, "offset": index},
                                  len(pending), final=index == total)
            pending = []
    if offset == total:
        yield CollectionBatch((), {"partition": partition, "digest": fingerprint, "offset": total}, 0, final=True)


def cached_batches(ctx, factory, cursor, *, partition, max_cache_bytes=2_000_000_000):
    """Freeze a large enumeration in a temporary spool before accepting writes.

    Source failures late in a season do not accept an incomplete enumeration.
    Only a game and a batch occupy memory; larger spools use temporary disk and
    are closed/deleted on cancellation, errors, or generator completion.
    """
    import json
    from tempfile import SpooledTemporaryFile
    from app.jobs.shared.data_contracts import SourceObservation
    from app.jobs.shared.validation import SourceRecord
    with SpooledTemporaryFile(max_size=1_000_000, mode="w+b") as cache:
        size, count = 0, 0
        for item in factory():
            encoded = canonical_json({"dataset": item.dataset, "payload": item.payload,
                                      "observation": item.observation.model_dump(mode="json")}) + b"\n"
            size += len(encoded)
            count += 1
            if size > max_cache_bytes or count > ctx.config.max_batches * ctx.config.max_batch_records:
                raise ValueError("Source enumeration exceeds bounded temporary cache/batch limits")
            cache.write(encoded)
        def records():
            cache.seek(0)
            for encoded in cache:
                item = json.loads(encoded)
                yield SourceRecord(item["dataset"], item["payload"],
                    SourceObservation.model_validate_json(canonical_json(item["observation"])))
        yield from stream_batches(ctx, records, cursor, partition=partition)

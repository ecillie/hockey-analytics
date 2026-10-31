"""Roster feed parsing, name normalization, and conservative identity matching."""

from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import date
from itertools import chain
import unicodedata
from urllib.error import URLError

from pydantic import BaseModel, ValidationError

from app.ScriptingFiles.FullDataScript.roster_status.domain import (
    ExternalRosterPlayer,
    StoredPlayer,
)
from app.ScriptingFiles.FullDataScript.roster_status.errors import (
    FeedFetchError,
    InvalidJsonResponseError,
)
from app.ScriptingFiles.FullDataScript.roster_status.http_json_client import JsonClient
from app.ScriptingFiles.FullDataScript.roster_status.schemas import AhlRoster, NhlRoster


def fetch_validated[T: BaseModel](
    client: JsonClient,
    url: str,
    model: type[T],
    source: str,
    params: Mapping[str, str] | None = None,
) -> T:
    try:
        return model.model_validate(client.get_json(url, params))
    except (
        URLError,
        OSError,
        UnicodeError,
        InvalidJsonResponseError,
        ValidationError,
    ) as exc:
        reason = (
            "response shape is invalid"
            if isinstance(exc, ValidationError)
            else str(exc)
        )
        raise FeedFetchError(source=source, reason=reason) from exc


def parse_nhl_roster(payload: NhlRoster, team: str) -> tuple[ExternalRosterPlayer, ...]:
    rows = chain(payload.forwards, payload.defensemen, payload.goalies)
    return tuple(
        ExternalRosterPlayer(
            external_id=str(row.id),
            full_name=f"{row.firstName.default} {row.lastName.default}".strip(),
            team_external_id=team,
        )
        for row in rows
    )


def parse_ahl_roster(payload: AhlRoster, team: str) -> tuple[ExternalRosterPlayer, ...]:
    rows = (
        entry.row
        for group in payload.roster
        for section in group.sections
        for entry in section.data
    )
    return tuple(
        ExternalRosterPlayer(
            external_id=str(row.player_id),
            full_name=row.name,
            birth_date=parse_birth_date(row.birthdate),
            team_external_id=team,
        )
        for row in rows
    )


def parse_birth_date(value: str | None) -> date | None:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return "".join(
        character for character in without_accents.casefold() if character.isalnum()
    )


def match_ahl_players(
    players: tuple[StoredPlayer, ...], ahl_players: tuple[ExternalRosterPlayer, ...]
) -> dict[int, ExternalRosterPlayer]:
    ahl_by_id = index_ahl_players(ahl_players)
    stored_counts = Counter(
        player.ahl_external_id
        for player in players
        if player.ahl_external_id is not None
    )
    matches = {
        player.id: ahl_by_id[player.ahl_external_id]
        for player in players
        if player.ahl_external_id in ahl_by_id
        and stored_counts[player.ahl_external_id] == 1
    }
    claimed_ids = {player.external_id for player in matches.values()}
    db_by_identity: dict[tuple[str, date], list[StoredPlayer]] = defaultdict(list)
    ahl_by_identity: dict[tuple[str, date], list[ExternalRosterPlayer]] = defaultdict(
        list
    )
    for player in players:
        if player.id not in matches and player.birth_date is not None:
            db_by_identity[
                (normalize_name(player.full_name), player.birth_date)
            ].append(player)
    for player in ahl_by_id.values():
        if player.birth_date is not None:
            ahl_by_identity[
                (normalize_name(player.full_name), player.birth_date)
            ].append(player)
    for identity, stored_candidates in db_by_identity.items():
        candidates = ahl_by_identity.get(identity, [])
        if len(stored_candidates) == 1 and len(candidates) == 1:
            candidate = candidates[0]
            if candidate.external_id not in claimed_ids:
                matches[stored_candidates[0].id] = candidate
    return matches


def index_ahl_players(
    players: tuple[ExternalRosterPlayer, ...],
) -> dict[str, ExternalRosterPlayer]:
    identities: dict[str, set[tuple[str, date | None]]] = defaultdict(set)
    for player in players:
        identities[player.external_id].add(
            (normalize_name(player.full_name), player.birth_date)
        )
    return {
        player.external_id: player
        for player in players
        if len(identities[player.external_id]) == 1
    }

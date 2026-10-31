"""CapWages active index and profile normalization without persistence."""

import re
from collections.abc import Iterable
from dataclasses import replace
from datetime import date
from decimal import ROUND_HALF_EVEN

from app.ScriptingFiles.FullDataScript.contracts.domain import (
    ActivePlayer,
    ParsedContract,
)
from app.ScriptingFiles.FullDataScript.contracts.errors import (
    ActiveContractError,
    ActiveSeasonSequenceError,
    CapSpaceParseError,
    ContractDocumentError,
    DocumentFailure,
    ProfileSlugError,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas import (
    parse_source_document,
    validate_page,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.contracts import (
    contract_from_mapping,
    mapping_rows,
    page_player,
)
from app.ScriptingFiles.FullDataScript.contracts.util import clean_text, optional_text
from app.ScriptingFiles.FullDataScript.source_ingestion.errors import RowCountViolation
from app.ScriptingFiles.FullDataScript.source_ingestion.util import slug_from_name


def capwages_birth_date(value: object) -> str | None:
    found = re.fullmatch(r"(\d{2})-(\d{1,2})-(\d{1,2})", clean_text(value))
    if found is None:
        return None
    year, month, day = map(int, found.groups())
    year += 1900 if year >= 30 else 2000
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_active_index(html: str, *, minimum_rows: int = 500) -> list[list[object]]:
    document = parse_source_document(html)
    pages = tuple(map(validate_page, document.next_data))
    rows = next(
        (page.playersArray for page in pages if page.playersArray is not None), None
    )
    if rows is None:
        raise ContractDocumentError(
            reason=DocumentFailure.INVALID_PAYLOAD,
            source="CapWages active-player page __NEXT_DATA__",
        )
    if len(rows) < minimum_rows:
        raise RowCountViolation(
            source="CapWages active-player list", actual=len(rows), minimum=minimum_rows
        )
    return rows


def active_player(row: list[object]) -> ActivePlayer | None:
    if len(row) < 4 or clean_text(row[0]) == "":
        return None
    slug = optional_text(row[1])
    if slug is None:
        slug = slug_from_name(clean_text(row[0]))
    if slug == "":
        return None
    return ActivePlayer(
        name=clean_text(row[0]),
        slug=slug,
        team=clean_text(row[2]),
        position=clean_text(row[3]),
        nationality=optional_text(row[7]) if len(row) > 7 else None,
        birth_date=capwages_birth_date(row[30]) if len(row) > 30 else None,
    )


def parse_active_players(
    rows: Iterable[list[object]], *, minimum_rows: int = 500
) -> tuple[ActivePlayer, ...]:
    players = tuple(
        player for row in rows if (player := active_player(row)) is not None
    )
    if len(players) < minimum_rows:
        raise RowCountViolation(
            source="CapWages profile slugs", actual=len(players), minimum=minimum_rows
        )
    return players


def parse_active_profile(html: str, *, slug: str) -> tuple[ParsedContract, ...]:
    document = parse_source_document(html)
    player = next(
        (row for payload in document.next_data if len(row := page_player(payload)) > 0),
        None,
    )
    if player is None or "contracts" not in player:
        raise ContractDocumentError(
            reason=DocumentFailure.INVALID_PAYLOAD, source="CapWages profile"
        )
    page_slug = clean_text(player.get("slug"))
    if page_slug != "" and page_slug != slug:
        raise ProfileSlugError(expected=slug, actual=page_slug)
    return tuple(
        parse_active_contract(raw, slug=slug)
        for raw in mapping_rows(player["contracts"])
    )


def parse_active_contract(raw: dict[str, object], *, slug: str) -> ParsedContract:
    try:
        contract = contract_from_mapping(raw, rounding=ROUND_HALF_EVEN)
    except CapSpaceParseError as error:
        raise ActiveContractError(slug=slug, failure=error) from error
    years = tuple(row.season_start_year for row in contract.seasons)
    unique = sorted(set(years))
    if len(unique) != len(years) or unique != list(range(unique[0], unique[-1] + 1)):
        raise ActiveSeasonSequenceError(slug=slug, years=years)
    return replace(contract, term_years=len(years))

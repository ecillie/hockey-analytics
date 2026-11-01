"""Contract JSON and rendered-table parsing independent of I/O."""

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import replace
from decimal import ROUND_HALF_UP
from itertools import takewhile

from app.ScriptingFiles.FullDataScript.contracts.domain import (
    ContractSeason,
    ParsedContract,
)
from app.ScriptingFiles.FullDataScript.contracts.errors import (
    CapSpaceParseError,
    ContractDocumentError,
    DocumentFailure,
    ProfileIdentityError,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.documents import PageSnapshots
from app.ScriptingFiles.FullDataScript.contracts.schemas import (
    SourceDocument,
    parse_source_document,
    tag_attribute,
    tag_text,
    validate_page,
)
from app.ScriptingFiles.FullDataScript.contracts.util import (
    clean_text,
    parse_contract_type,
    parse_signing_date,
    parse_expiry_status,
    is_entry_level,
    parse_money_cents,
    parse_optional_text,
    parse_season_start_year,
)
from bs4 import Tag


def extract_page_player(payload: dict[str, object]) -> dict[str, object]:
    page = validate_page(payload)
    if page.player is not None and len(page.player) > 0:
        return page.player
    return {} if page.person is None else page.person


def extract_embedded_nhl_id(payloads: PageSnapshots) -> str | None:
    identities = {
        str(identity)
        for payload in payloads
        if (identity := extract_page_player(payload).get("nhlId")) is not None
    }
    if len(identities) > 1:
        raise ContractDocumentError(
            reason=DocumentFailure.INVALID_PAYLOAD, source="conflicting NHL identities"
        )
    return next(iter(identities), None)


def parse_mapping_season(
    row: Mapping[str, object], *, rounding: str = ROUND_HALF_UP
) -> ContractSeason:
    normalized = {
        re.sub(r"[^a-z]", "", key.lower()): value for key, value in row.items()
    }
    year = parse_season_start_year(normalized.get("season"))
    cap_hit = parse_money_cents(
        normalized.get("caphit", normalized.get("caphitcents")), rounding=rounding
    )
    if cap_hit is None:
        raise ContractDocumentError(
            reason=DocumentFailure.MISSING_CAP_HIT, source=str(row.get("season"))
        )
    salary = normalized.get("nhlsalary", normalized.get("basesalary"))
    slide = (
        "slide" in clean_text(salary).lower()
        or "slide" in clean_text(normalized.get("type")).lower()
    )
    return ContractSeason(
        season_start_year=year,
        cap_hit_cents=cap_hit,
        base_salary_cents=None
        if slide
        else parse_money_cents(salary, rounding=rounding),
        signing_bonus_cents=parse_money_cents(
            normalized.get("signingbonus", normalized.get("signingbonuses")),
            rounding=rounding,
        ),
        performance_bonus_cents=parse_money_cents(
            normalized.get(
                "performancebonus",
                normalized.get(
                    "performancebonuses",
                    normalized.get("perfbonus", normalized.get("perfbonuses")),
                ),
            ),
            rounding=rounding,
        ),
        minors_salary_cents=parse_money_cents(
            normalized.get("minorssalary"), rounding=rounding
        ),
        clause=parse_optional_text(normalized.get("clause")),
        owning_team=parse_optional_text(
            normalized.get("owningteam", normalized.get("team"))
        ),
        is_slide=slide,
        source_snapshot=json.dumps(dict(row)),
    )


def extract_mapping_rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ContractDocumentError(
            reason=DocumentFailure.INVALID_PAYLOAD, source="contract rows"
        )
    return value


def extract_mapping_value(
    row: Mapping[str, object], keys: tuple[str, ...], default: object = None
) -> object:
    return next(
        (
            value
            for key in keys
            if (value := row.get(key)) is not None
            and value != ""
            and value != []
            and value != {}
        ),
        default,
    )


def parse_mapping_contract(
    raw: dict[str, object], *, rounding: str = ROUND_HALF_UP
) -> ParsedContract:
    details = extract_mapping_value(raw, ("details", "seasons"), [])
    seasons = tuple(
        parse_mapping_season(row, rounding=rounding)
        for row in extract_mapping_rows(details)
    )
    if len(seasons) == 0 or len({row.season_start_year for row in seasons}) != len(
        seasons
    ):
        raise ContractDocumentError(
            reason=DocumentFailure.INVALID_SEASONS, source="embedded JSON"
        )
    term_value = extract_mapping_value(
        raw, ("term", "termYears", "seasonsCount"), len(seasons)
    )
    try:
        term = int(str(term_value))
    except ValueError as error:
        raise ContractDocumentError(
            reason=DocumentFailure.INVALID_SEASONS, source="contract term"
        ) from error
    if term <= 0:
        raise ContractDocumentError(
            reason=DocumentFailure.INVALID_SEASONS, source="contract term"
        )
    kind = extract_mapping_value(raw, ("type", "contractType"))
    return ParsedContract(
        contract_type=parse_contract_type(kind),
        is_entry_level=is_entry_level(kind),
        total_value_cents=parse_money_cents(
            extract_mapping_value(raw, ("value", "totalValue")), rounding=rounding
        ),
        term_years=term,
        signed_on=parse_signing_date(
            extract_mapping_value(raw, ("signingDate", "signed_on"))
        ),
        signing_team=parse_optional_text(
            extract_mapping_value(raw, ("signingTeam", "team"))
        ),
        expiry_status=parse_expiry_status(
            extract_mapping_value(raw, ("expiryStatus", "expiry"))
        ),
        seasons=seasons,
        external_id=parse_optional_text(
            extract_mapping_value(raw, ("id", "contractId"))
        ),
        source_snapshot=json.dumps(raw),
    )


def parse_json_contracts(payload: dict[str, object]) -> list[ParsedContract] | None:
    page = validate_page(payload)
    person = (
        page.person
        if page.person is not None and len(page.person) > 0
        else extract_page_player(payload)
    )
    raw_contracts = extract_mapping_value(person, ("contracts",), page.contracts)
    if person.get("contracts") == [] and page.contracts is None:
        raw_contracts = []
    if raw_contracts is None:
        return None
    return list(map(parse_mapping_contract, extract_mapping_rows(raw_contracts)))


def extract_table_cells(row: Tag) -> list[str]:
    return [tag_text(cell) for cell in row.find_all(["th", "td"], recursive=False)]


def is_primary_row(values: list[str]) -> bool:
    return len(values) == 0 or not values[0].lower().startswith(
        ("buyout years", "termination fees", "cap recapture")
    )


def parse_season_table_rows(table: Tag) -> list[dict[str, str]]:
    rows = list(table.find_all("tr"))
    header = next(
        (
            (index, cells)
            for index, row in enumerate(rows)
            if "season"
            in (
                cells := [
                    re.sub(r"[^a-z]", "", cell.lower())
                    for cell in extract_table_cells(row)
                ]
            )
            and "caphit" in cells
        ),
        None,
    )
    if header is None:
        return []
    index, columns = header
    primary_rows = takewhile(
        is_primary_row, map(extract_table_cells, rows[index + 1 :])
    )
    return [
        dict(zip(columns, values))
        for values in primary_rows
        if len(values) > 0
        and re.fullmatch(r"\d{4}\s*[-–—]\s*(?:\d{2}|\d{4})", values[0]) is not None
    ]


def extract_table_rows(block: Tag) -> list[dict[str, str]]:
    return next(
        (
            rows
            for table in block.find_all("table")
            if len(rows := parse_season_table_rows(table)) > 0
        ),
        [],
    )


def extract_metadata_value(text: str, label: str) -> str | None:
    found = re.search(
        rf"{label}\s*:\s*(.*?)(?=\s*\|\s*|\s+(?:Seasons?|Signing Date|Signing Team|Expiration Status|Season\s+Cap Hit)\b|$)",
        text,
        re.I,
    )
    return None if found is None else found.group(1).strip()


def parse_table_contract(block: Tag) -> ParsedContract | None:
    text = tag_text(block)
    rows = extract_table_rows(block)
    if len(rows) == 0:
        return None
    seasons = tuple(map(parse_mapping_season, rows))
    if len(seasons) == 0 or len({row.season_start_year for row in seasons}) != len(
        seasons
    ):
        raise ContractDocumentError(
            reason=DocumentFailure.INVALID_SEASONS, source="HTML table"
        )
    heading = next(
        (
            tag_text(node)
            for node in block.find_all(["h2", "h3", "h4"])
            if "contract" in tag_text(node).lower()
        ),
        None,
    )
    kind = parse_contract_type(heading)
    term = extract_metadata_value(text, "Seasons?")
    if term is not None and (not term.isdigit() or int(term) <= 0):
        raise ContractDocumentError(
            reason=DocumentFailure.INVALID_SEASONS, source="HTML term"
        )
    return ParsedContract(
        contract_type=kind,
        is_entry_level=is_entry_level(kind),
        total_value_cents=parse_money_cents(
            extract_metadata_value(text, "Total Value")
        ),
        term_years=len(seasons) if term is None else int(term),
        signed_on=parse_signing_date(extract_metadata_value(text, "Signing Date")),
        signing_team=extract_metadata_value(text, "Signing Team"),
        expiry_status=parse_expiry_status(
            extract_metadata_value(text, "Expiration Status")
        ),
        seasons=seasons,
        external_id=next(
            (
                value
                for key in ("data-contract-id", "data-external-id")
                if (value := parse_optional_text(tag_attribute(block, key))) is not None
            ),
            None,
        ),
        source_snapshot=json.dumps({"text": text, "rows": rows}),
    )


def parse_document_contracts(
    document: SourceDocument, pages: PageSnapshots
) -> list[ParsedContract]:
    parsed_json: list[ParsedContract] | None = None
    failure: CapSpaceParseError | None = None
    payloads = iter(pages)
    while (parsed_json is None or len(parsed_json) == 0) and (
        payload := next(payloads, None)
    ) is not None:
        try:
            parsed_json = parse_json_contracts(payload)
        except CapSpaceParseError as error:
            failure = error
    if parsed_json is not None and len(parsed_json) > 0:
        return parsed_json
    candidates = document.root.select("article, .contract, .contract-block")
    blocks = [
        node
        for node in candidates
        if "Total Value" in tag_text(node)
        and node.find("table") is not None
        and not any(parent in candidates for parent in node.parents)
    ]
    if len(blocks) > 0:
        contracts = [
            contract
            for block in blocks
            if (contract := parse_table_contract(block)) is not None
        ]
        if len(contracts) > 0:
            return contracts
        raise ContractDocumentError(
            reason=DocumentFailure.INVALID_SEASONS, source="HTML table"
        )
    if failure is not None:
        raise failure
    if parsed_json == []:
        return []
    if len(document.root.find_all("script", id="__NEXT_DATA__")) > 0:
        raise ContractDocumentError(
            reason=DocumentFailure.INVALID_PAYLOAD, source="embedded JSON"
        )
    if (
        re.search(
            r"Contract History|No recorded contracts", tag_text(document.root), re.I
        )
        and document.root.find("table") is None
    ):
        return []
    raise ContractDocumentError(reason=DocumentFailure.UNRECOGNIZED, source="CapSpace")


def parse_contract_document(
    document: SourceDocument,
    *,
    expected_nhl_id: str | None = None,
    require_nhl_id: bool = False,
    pages: PageSnapshots | None = None,
) -> tuple[ParsedContract, ...]:
    payloads = document.next_data if pages is None else pages
    if expected_nhl_id is not None:
        actual = extract_embedded_nhl_id(payloads)
        if (require_nhl_id and actual is None) or (
            actual is not None and actual != expected_nhl_id
        ):
            raise ProfileIdentityError(expected=expected_nhl_id, actual=actual)
    return tuple(parse_document_contracts(document, payloads))


def parse_capspace_page(
    html: str, *, expected_nhl_id: str | None = None, require_nhl_id: bool = False
) -> tuple[ParsedContract, ...]:
    if html.strip() == "":
        raise ContractDocumentError(reason=DocumentFailure.EMPTY, source="CapSpace")
    return parse_contract_document(
        parse_source_document(html),
        expected_nhl_id=expected_nhl_id,
        require_nhl_id=require_nhl_id,
    )


def normalize_contracts(
    contracts: Iterable[ParsedContract], nhl_id: str, source_code: str = "capspace"
) -> tuple[ParsedContract, ...]:
    normalized = []
    for index, contract in enumerate(contracts):
        first = min(row.season_start_year for row in contract.seasons)
        last = max(row.season_start_year for row in contract.seasons)
        external_id = contract.external_id
        if external_id is None or external_id == "":
            external_id = f"{source_code}:{nhl_id}:{first}:{last}:{index}"
        normalized.append(replace(contract, external_id=external_id))
    return tuple(normalized)

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
from app.ScriptingFiles.FullDataScript.contracts.schemas import (
    SourceDocument,
    parse_source_document,
    tag_attribute,
    tag_text,
    validate_page,
)
from app.ScriptingFiles.FullDataScript.contracts.util import (
    clean_text,
    contract_type,
    date_value,
    expiry_status,
    is_entry_level,
    money_to_cents,
    optional_text,
    season_start_year,
)
from bs4 import Tag


def page_player(payload: dict[str, object]) -> dict[str, object]:
    page = validate_page(payload)
    if page.player is not None and len(page.player) > 0:
        return page.player
    return {} if page.person is None else page.person


def embedded_nhl_id(document: SourceDocument) -> str | None:
    identities = {
        str(identity)
        for payload in document.next_data
        if (identity := page_player(payload).get("nhlId")) is not None
    }
    if len(identities) > 1:
        raise ContractDocumentError(
            reason=DocumentFailure.INVALID_PAYLOAD, source="conflicting NHL identities"
        )
    return next(iter(identities), None)


def season_from_mapping(
    row: Mapping[str, object], *, rounding: str = ROUND_HALF_UP
) -> ContractSeason:
    normalized = {
        re.sub(r"[^a-z]", "", key.lower()): value for key, value in row.items()
    }
    year = season_start_year(normalized.get("season"))
    cap_hit = money_to_cents(
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
        base_salary_cents=None if slide else money_to_cents(salary, rounding=rounding),
        signing_bonus_cents=money_to_cents(
            normalized.get("signingbonus", normalized.get("signingbonuses")),
            rounding=rounding,
        ),
        performance_bonus_cents=money_to_cents(
            normalized.get(
                "performancebonus",
                normalized.get(
                    "performancebonuses",
                    normalized.get("perfbonus", normalized.get("perfbonuses")),
                ),
            ),
            rounding=rounding,
        ),
        minors_salary_cents=money_to_cents(
            normalized.get("minorssalary"), rounding=rounding
        ),
        clause=optional_text(normalized.get("clause")),
        owning_team=optional_text(normalized.get("owningteam", normalized.get("team"))),
        is_slide=slide,
        source_snapshot=json.dumps(dict(row)),
    )


def mapping_rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ContractDocumentError(
            reason=DocumentFailure.INVALID_PAYLOAD, source="contract rows"
        )
    return value


def mapping_value(
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


def contract_from_mapping(
    raw: dict[str, object], *, rounding: str = ROUND_HALF_UP
) -> ParsedContract:
    details = mapping_value(raw, ("details", "seasons"), [])
    seasons = tuple(
        season_from_mapping(row, rounding=rounding) for row in mapping_rows(details)
    )
    if len(seasons) == 0 or len({row.season_start_year for row in seasons}) != len(
        seasons
    ):
        raise ContractDocumentError(
            reason=DocumentFailure.INVALID_SEASONS, source="embedded JSON"
        )
    term_value = mapping_value(raw, ("term", "termYears", "seasonsCount"), len(seasons))
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
    kind = mapping_value(raw, ("type", "contractType"))
    return ParsedContract(
        contract_type=contract_type(kind),
        is_entry_level=is_entry_level(kind),
        total_value_cents=money_to_cents(
            mapping_value(raw, ("value", "totalValue")), rounding=rounding
        ),
        term_years=term,
        signed_on=date_value(mapping_value(raw, ("signingDate", "signed_on"))),
        signing_team=optional_text(mapping_value(raw, ("signingTeam", "team"))),
        expiry_status=expiry_status(mapping_value(raw, ("expiryStatus", "expiry"))),
        seasons=seasons,
        external_id=optional_text(mapping_value(raw, ("id", "contractId"))),
        source_snapshot=json.dumps(raw),
    )


def contracts_from_json(payload: dict[str, object]) -> list[ParsedContract] | None:
    page = validate_page(payload)
    person = (
        page.person
        if page.person is not None and len(page.person) > 0
        else page_player(payload)
    )
    raw_contracts = mapping_value(person, ("contracts",), page.contracts)
    if person.get("contracts") == [] and page.contracts is None:
        raw_contracts = []
    if raw_contracts is None:
        return None
    return list(map(contract_from_mapping, mapping_rows(raw_contracts)))


def table_cells(row: Tag) -> list[str]:
    return [tag_text(cell) for cell in row.find_all(["th", "td"], recursive=False)]


def is_primary_row(values: list[str]) -> bool:
    return len(values) == 0 or not values[0].lower().startswith(
        ("buyout years", "termination fees", "cap recapture")
    )


def season_table_rows(table: Tag) -> list[dict[str, str]]:
    rows = list(table.find_all("tr"))
    header = next(
        (
            (index, cells)
            for index, row in enumerate(rows)
            if "season"
            in (
                cells := [
                    re.sub(r"[^a-z]", "", cell.lower()) for cell in table_cells(row)
                ]
            )
            and "caphit" in cells
        ),
        None,
    )
    if header is None:
        return []
    index, columns = header
    primary_rows = takewhile(is_primary_row, map(table_cells, rows[index + 1 :]))
    return [
        dict(zip(columns, values))
        for values in primary_rows
        if len(values) > 0
        and re.fullmatch(r"\d{4}\s*[-–—]\s*(?:\d{2}|\d{4})", values[0]) is not None
    ]


def table_rows(block: Tag) -> list[dict[str, str]]:
    return next(
        (
            rows
            for table in block.find_all("table")
            if len(rows := season_table_rows(table)) > 0
        ),
        [],
    )


def metadata_value(text: str, label: str) -> str | None:
    found = re.search(
        rf"{label}\s*:\s*(.*?)(?=\s*\|\s*|\s+(?:Seasons?|Signing Date|Signing Team|Expiration Status|Season\s+Cap Hit)\b|$)",
        text,
        re.I,
    )
    return None if found is None else found.group(1).strip()


def contract_from_table(block: Tag) -> ParsedContract | None:
    text = tag_text(block)
    rows = table_rows(block)
    if len(rows) == 0:
        return None
    seasons = tuple(map(season_from_mapping, rows))
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
    kind = contract_type(heading)
    term = metadata_value(text, "Seasons?")
    if term is not None and (not term.isdigit() or int(term) <= 0):
        raise ContractDocumentError(
            reason=DocumentFailure.INVALID_SEASONS, source="HTML term"
        )
    return ParsedContract(
        contract_type=kind,
        is_entry_level=is_entry_level(kind),
        total_value_cents=money_to_cents(metadata_value(text, "Total Value")),
        term_years=len(seasons) if term is None else int(term),
        signed_on=date_value(metadata_value(text, "Signing Date")),
        signing_team=metadata_value(text, "Signing Team"),
        expiry_status=expiry_status(metadata_value(text, "Expiration Status")),
        seasons=seasons,
        external_id=next(
            (
                value
                for key in ("data-contract-id", "data-external-id")
                if (value := optional_text(tag_attribute(block, key))) is not None
            ),
            None,
        ),
        source_snapshot=json.dumps({"text": text, "rows": rows}),
    )


def document_contracts(document: SourceDocument) -> list[ParsedContract]:
    parsed_json: list[ParsedContract] | None = None
    failure: CapSpaceParseError | None = None
    payloads = iter(document.next_data)
    while (parsed_json is None or len(parsed_json) == 0) and (
        payload := next(payloads, None)
    ) is not None:
        try:
            parsed_json = contracts_from_json(payload)
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
            if (contract := contract_from_table(block)) is not None
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
) -> tuple[ParsedContract, ...]:
    if expected_nhl_id is not None:
        actual = embedded_nhl_id(document)
        if (require_nhl_id and actual is None) or (
            actual is not None and actual != expected_nhl_id
        ):
            raise ProfileIdentityError(expected=expected_nhl_id, actual=actual)
    return tuple(document_contracts(document))


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

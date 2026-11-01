"""Exact source amount, season, text, and signing date conversion."""

import json
import re
from collections import Counter
from collections.abc import Iterable
from app.ScriptingFiles.FullDataScript.contracts.domain import (
    Candidate,
    ProfileResult,
    ProfileSource,
    ProfileStatus,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.serialization import (
    serialize_contract,
)
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, DecimalException, InvalidOperation

from app.ScriptingFiles.FullDataScript.contracts.errors import (
    MoneyFailure,
    MoneyParseError,
    SeasonParseError,
    SigningDateParseError,
)
from dateutil.parser import parse as parse_date


def parse_money_cents(value: object, *, rounding: str = ROUND_HALF_UP) -> int | None:
    if value is None or str(value).strip() in {"", "-", "—", "–", "N/A", "NA"}:
        return None
    text = str(value).strip().replace("$", "").replace(",", "").replace(" ", "")
    try:
        amount = Decimal(text)
    except InvalidOperation as error:
        raise MoneyParseError(
            value=str(value), reason=MoneyFailure.MALFORMED
        ) from error
    if not amount.is_finite():
        raise MoneyParseError(value=str(value), reason=MoneyFailure.NONFINITE)
    if amount < 0:
        raise MoneyParseError(value=str(value), reason=MoneyFailure.NEGATIVE)
    try:
        return int((amount * 100).quantize(Decimal("1"), rounding=rounding))
    except DecimalException as error:
        raise MoneyParseError(
            value=str(value), reason=MoneyFailure.UNREPRESENTABLE
        ) from error


def parse_season_start_year(value: object) -> int:
    text = clean_text(value).replace("–", "-").replace("—", "-")
    found = re.fullmatch(r"(\d{4})\s*-\s*(\d{2}|\d{4})", text)
    if found is None:
        raise SeasonParseError(value=str(value))
    year = int(found.group(1))
    end = found.group(2)
    expected_end = str(year + 1) if len(end) == 4 else f"{(year + 1) % 100:02d}"
    if year < 1900 or year > 2200 or end != expected_end:
        raise SeasonParseError(value=str(value))
    return year


def clean_text(value: object) -> str:
    return " ".join(str("" if value is None else value).replace("\xa0", " ").split())


def parse_optional_text(value: object) -> str | None:
    text = clean_text(value)
    return text if text != "" else None


def parse_signing_date(value: object) -> date | None:
    text = clean_text(value)
    if text == "":
        return None
    if found := re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text):
        return build_calendar_date(value, tuple(map(int, found.groups())))
    if found := re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text):
        month, day, year = map(int, found.groups())
        return build_calendar_date(value, (year, month, day))
    if re.fullmatch(r"[A-Za-z]{3,9}\.?\s+\d{1,2},\s*\d{4}", text) is None:
        raise SigningDateParseError(value=str(value))
    try:
        return parse_date(text).date()
    except ValueError as error:
        raise SigningDateParseError(value=str(value)) from error


def build_calendar_date(value: object, parts: tuple[int, ...]) -> date:
    try:
        return date(*parts)
    except ValueError as error:
        raise SigningDateParseError(value=str(value)) from error


def parse_expiry_status(value: object) -> str | None:
    text = clean_text(value).upper()
    return next((status for status in ("RFA", "UFA") if status in text), None)


def parse_contract_type(value: object) -> str | None:
    text = clean_text(value)[:32]
    return text if text != "" else None


def is_entry_level(value: object) -> bool:
    text = clean_text(value).upper()
    return "ENTRY" in text or "ELC" in text


def decode_snapshot(snapshot: str | None) -> dict[str, object] | None:
    if snapshot is None:
        return None
    return json.loads(snapshot)


type SourceProfileRecords = dict[str, list[tuple[Candidate, dict[str, object]]]]


def serialize_profile_result(result: ProfileResult) -> dict[str, object]:
    return {
        "status": result.status,
        "error": result.error,
        "url": result.url,
        "contracts": [serialize_contract(contract) for contract in result.contracts],
    }


def group_source_records(
    candidates: Iterable[Candidate],
    results: Iterable[ProfileResult],
) -> SourceProfileRecords:
    grouped: SourceProfileRecords = {
        ProfileSource.CAPSPACE: [
            (candidate, {"status": ProfileStatus.NO_NHL_ID})
            for candidate in candidates
            if candidate.nhl_id in (None, "")
        ]
    }
    for result in results:
        grouped.setdefault(result.source_code, []).append(
            (result.candidate, serialize_profile_result(result))
        )
    return grouped


def calculate_profile_metrics(results: Iterable[ProfileResult]) -> Counter[str]:
    materialized = list(results)
    return Counter(
        {
            "profiles_succeeded": sum(
                result.status == ProfileStatus.SUCCEEDED for result in materialized
            ),
            "profiles_with_target_coverage": sum(
                result.covers_target for result in materialized
            ),
            "profiles_not_found": sum(
                result.status == ProfileStatus.NOT_FOUND for result in materialized
            ),
            "profiles_failed": sum(
                result.status in (ProfileStatus.FAILED, ProfileStatus.PARSE_FAILED)
                for result in materialized
            ),
            "profiles_no_contracts": sum(
                result.status == ProfileStatus.NO_CONTRACTS for result in materialized
            ),
            "profiles_no_matching_contracts": sum(
                result.status == ProfileStatus.NO_MATCHING_CONTRACTS
                for result in materialized
            ),
            "capspace_profiles_succeeded": sum(
                result.status == ProfileStatus.SUCCEEDED
                and result.source_code == ProfileSource.CAPSPACE
                for result in materialized
            ),
            "capwages_profiles_succeeded": sum(
                result.status == ProfileStatus.SUCCEEDED
                and result.source_code == ProfileSource.CAPWAGES
                for result in materialized
            ),
            "capwages_fallbacks_attempted": sum(
                result.fallback_attempted for result in materialized
            ),
            "capwages_fallbacks_failed": sum(
                result.fallback_status
                in (ProfileStatus.FAILED, ProfileStatus.PARSE_FAILED)
                for result in materialized
            ),
            "capwages_fallbacks_not_found": sum(
                result.fallback_status == ProfileStatus.NOT_FOUND
                for result in materialized
            ),
            "contracts_parsed": sum(len(result.contracts) for result in materialized),
        }
    )


def count_unprocessed_records(summary: dict[str, int]) -> int:
    return (
        summary.get("records_skipped", 0)
        + summary.get("players_without_nhl_ids", 0)
        + summary.get("profiles_failed", 0)
        + summary.get("profiles_not_found", 0)
    )

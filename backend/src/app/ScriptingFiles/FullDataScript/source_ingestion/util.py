"""Shared source normalization and stable snapshot serialization."""

from datetime import date
from app.shared.calendar import latest_started_season
from decimal import Decimal, InvalidOperation
from math import isfinite
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata

from app.ScriptingFiles.FullDataScript.source_ingestion.errors import (
    PayloadViolation,
)


def season_start_year(as_of: date | None = None) -> int:
    value = date.today() if as_of is None else as_of
    return latest_started_season(value)


def ordered_team_abbreviations(value: object) -> tuple[str, ...]:
    return tuple(
        abbreviation
        for item in str("" if value is None else value).split(",")
        if (abbreviation := parse_team_abbreviation(item)) is not None
    )


def parse_team_abbreviation(value: object) -> str | None:
    if value is None:
        return None
    abbreviation = str(value).strip().upper()
    return (
        abbreviation
        if re.fullmatch(r"[A-Z]{2,4}", abbreviation) is not None
        and abbreviation not in {"ALL", "TOT"}
        else None
    )


def split_name(full_name: str) -> tuple[str, str]:
    name = " ".join(full_name.strip().split())
    if "," in name:
        last, first = (part.strip() for part in name.split(",", 1))
        return first, last
    first, separator, last = name.partition(" ")
    return first, last if separator != "" else "Unknown"


def normalize_position(value: object, goalie: bool = False) -> str | None:
    if goalie:
        return "G"
    text = str("" if value is None else value).upper().split(",", 1)[0].strip()
    return {"L": "LW", "R": "RW"}.get(
        text, text if text in {"C", "LW", "RW", "D", "G", "F"} else None
    )


def normalize_nationality(value: object) -> str | None:
    match = re.search(r"[A-Z]{3}", str("" if value is None else value).upper())
    return match.group(0) if match is not None else None


def parse_number(value: object, integer: bool = False) -> int | float | None:
    if value in (None, "", "NA", "N/A"):
        return None
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            return None
        result = int(number) if integer else float(number)
        return result if isinstance(result, int) or isfinite(result) else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_strict_integer(value: object) -> int | None:
    try:
        parsed = Decimal(str(value))
        if parsed.is_finite() and parsed == parsed.to_integral_value():
            return int(parsed)
    except (InvalidOperation, ValueError, TypeError):
        pass
    return None


def slug_from_name(name: str) -> str:
    first, last = split_name(name)
    ascii_name = (
        unicodedata.normalize("NFKD", f"{first} {last}")
        .encode("ascii", "ignore")
        .decode()
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_name.lower())).strip("-")


def source_row_hash(row: dict[str, object]) -> str:
    encoded = json.dumps(
        row, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def parse_csv(text: str, *, source: str) -> list[dict[str, object]]:
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames
    if fieldnames is None:
        fieldnames = []
    duplicates = sorted({name for name in fieldnames if fieldnames.count(name) > 1})
    if len(duplicates) > 0:
        raise PayloadViolation(
            source=source, reason=f"duplicate CSV columns: {', '.join(duplicates)}"
        )
    rows = list(reader)
    if any(None in row for row in rows):
        raise PayloadViolation(
            source=source, reason="malformed CSV row has too many values"
        )
    return rows


def read_csv(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return parse_csv(handle.read(), source=str(path))

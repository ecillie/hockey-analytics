"""Explicit, lossless common transforms; adapters choose source field mappings."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import re


def text(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Text normalization requires a string")
    return value.strip() or None


def _source_value(value):
    """Apply the same whitespace/missing-value rule before every typed transform."""
    return text(value) if isinstance(value, str) else value


def integer(value):
    value = _source_value(value)
    if value is None:
        return None
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value):
        return int(value)
    raise ValueError("Expected an integer, without rounding")


def money_cents(value):
    """Source USD dollars -> exact cents. Unknown stays None; no implicit rounding."""
    value = _source_value(value)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not money")
    try:
        amount = Decimal(str(value)) * 100
    except InvalidOperation as exc:
        raise ValueError("Invalid money") from exc
    if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
        raise ValueError("Money requires nonnegative, exact cents")
    return int(amount)


def iso_date(value):
    value = _source_value(value)
    if value is None:
        return None
    if type(value) is date:
        return value
    if not isinstance(value, str):
        raise ValueError("Expected an ISO date")
    return date.fromisoformat(value)


def utc_timestamp(value):
    value = _source_value(value)
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("Timestamp requires an explicit timezone")
    return value.astimezone(timezone.utc)


def seconds(value):
    """Convert a source MM:SS duration; numeric seconds must be explicit upstream."""
    value = _source_value(value)
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d+:[0-5]\d", value):
        raise ValueError("Expected MM:SS duration")
    minutes, remainder = value.split(":")
    return float(int(minutes) * 60 + int(remainder))

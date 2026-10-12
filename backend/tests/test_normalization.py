"""Exact common ETL transforms preserve missing values and reject lossy conversion."""
import pytest

from app.jobs.shared.normalization import integer, iso_date, money_cents, seconds, text, utc_timestamp
from .execution_fixtures import NOW


@pytest.mark.parametrize("value, expected", [(None, None), ("", None), ("0", 0), ("12.34", 1234)])
def test_money_preserves_unknown_zero_and_exact_units(value, expected):
    assert money_cents(value) == expected



@pytest.mark.parametrize("value", [True, "1.234", "NaN", "-1", "garbage"])
def test_money_rejects_invalid_or_lossy_values(value):
    with pytest.raises(ValueError):
        money_cents(value)



def test_normalization_does_not_invent_values_or_timezones():
    assert text("   ") is None and text(" x ") == "x"
    assert integer(" 7 ") == 7 and integer(None) is None
    assert seconds("12:30") == 750.0 and seconds(None) is None
    assert str(iso_date("2026-10-12")) == "2026-10-12"
    assert utc_timestamp("2026-10-12T14:00:00-04:00") == NOW
    for function, value in ((integer, True), (integer, "1.2"), (seconds, "1:60"),
                            (iso_date, NOW), (utc_timestamp, "2026-10-12T14:00:00")):
        with pytest.raises(ValueError):
            function(value)



def test_all_optional_transforms_treat_blank_cells_consistently():
    for transform in (integer, money_cents, iso_date, utc_timestamp, seconds):
        assert transform(None) is None
        assert transform(" \t ") is None
    assert iso_date(" 2026-10-12 ").isoformat() == "2026-10-12"
    assert seconds(" 12:30 ") == 750.0

"""Currency and season input spaces for contract boundaries."""

from decimal import Decimal

from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy


def currency_amounts(*, negative: bool = False) -> SearchStrategy[Decimal]:
    return st.decimals(
        min_value=-100_000_000 if negative else 0,
        max_value=Decimal("-0.01") if negative else 100_000_000,
        places=2,
        allow_nan=False,
        allow_infinity=False,
    )


def season_years() -> SearchStrategy[int]:
    return st.integers(min_value=1900, max_value=2200)

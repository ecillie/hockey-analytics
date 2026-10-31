"""Numeric source values including missing and non-finite boundaries."""

from decimal import Decimal

from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy


def optional_numbers() -> SearchStrategy[Decimal]:
    return st.decimals(allow_nan=True, allow_infinity=True)

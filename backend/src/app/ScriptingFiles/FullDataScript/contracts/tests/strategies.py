"""Currency and season input spaces for contract boundaries."""

from decimal import Decimal
from dataclasses import dataclass

from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy


@dataclass(slots=True, kw_only=True, frozen=True)
class CurrencyExample:
    amount: Decimal

    @property
    def text(self) -> str:
        return f"${self.amount:,.2f}"

    @property
    def cents(self) -> int:
        return int(self.amount * 100)


@dataclass(slots=True, kw_only=True, frozen=True)
class SeasonExample:
    year: int

    @property
    def short(self) -> str:
        return f"{self.year}-{(self.year + 1) % 100:02d}"

    @property
    def full(self) -> str:
        return f"{self.year}–{self.year + 1}"


def currency_examples() -> SearchStrategy[CurrencyExample]:
    return st.builds(CurrencyExample, amount=currency_amounts())


def season_examples() -> SearchStrategy[SeasonExample]:
    return st.builds(SeasonExample, year=season_years())


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

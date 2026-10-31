"""Calendar visibility and existing salary-cap estimation policy."""

from datetime import date


def buried_relief_cents(season: int) -> int:
    if season < 2013:
        return 0
    minimums = (
        (2015, 55_000_000),
        (2017, 57_500_000),
        (2019, 65_000_000),
        (2021, 70_000_000),
        (2023, 75_000_000),
        (2026, 77_500_000),
    )
    minimum_salary_cents = next(
        (amount for cutoff, amount in minimums if season < cutoff), 85_000_000
    )
    return minimum_salary_cents + 37_500_000


def latest_started_season(as_of: date) -> int:
    return as_of.year if as_of.month >= 7 else as_of.year - 1

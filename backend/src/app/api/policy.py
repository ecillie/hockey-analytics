"""Calendar visibility and existing salary-cap estimation policy."""

from app.shared.calendar import get_latest_started_season


def calculate_buried_relief_cents(season: int) -> int:
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


latest_started_season = get_latest_started_season

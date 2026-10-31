import pandas as pd
from app.config import get_database_settings
from app.database import database_resources
from sqlalchemy import Connection, text

SALARY_CAP_QUERY = """
SELECT
    start_year AS season,
    end_year,
    label AS season_label,
    salary_cap_cents,
    salary_cap_cents / 100.0 AS salary_cap_dollars

FROM seasons

WHERE salary_cap_cents IS NOT NULL

ORDER BY start_year;
"""


def load_salary_cap(*, connection: Connection | None = None) -> pd.DataFrame:

    if connection is None:
        with (
            database_resources(get_database_settings()) as resources,
            resources.engine.connect() as owned,
        ):
            return load_salary_cap(connection=owned)
    return pd.read_sql(text(SALARY_CAP_QUERY), connection)


if __name__ == "__main__":
    df = load_salary_cap()

    print("\n=== SALARY CAP DATA ===")
    print(f"Rows: {len(df):,}")

    if not df.empty:
        print(f"Seasons: {df['season'].min()} - {df['season'].max()}")

        print("\nSalary caps:")
        print(
            df[
                [
                    "season",
                    "season_label",
                    "salary_cap_dollars",
                ]
            ].to_string(index=False)
        )

"""Conversion of immutable query results into API response values."""

from app.api.domain import (
    IdentityRow,
    SummaryRow,
    TeamRow,
    ContractSeasonRow,
    PlayerIdentityData,
    PlayerSummaryData,
    TeamSummaryData,
    ContractSeasonData,
)


def identity_data(row: IdentityRow | SummaryRow) -> PlayerIdentityData:
    return {
        "id": row.id,
        "firstName": row.first_name,
        "lastName": row.last_name,
        "fullName": row.full_name,
        "birthDate": row.birth_date,
        "age": row.age,
        "primaryPosition": row.primary_position,
        "shootsCatches": row.shoots_catches,
        "nationality": row.nationality,
        "active": row.active,
        "rosterStatus": row.roster_status,
        "team": player_team_data(row),
    }


def summary_data(row: SummaryRow) -> PlayerSummaryData:
    return {
        **identity_data(row),
        "season": row.season,
        "gamesPlayed": row.games_played,
        "goals": row.goals,
        "assists": row.assists,
        "points": row.points,
        "toiSeconds": round(row.ice_time_seconds)
        if row.ice_time_seconds is not None
        else None,
        "gameScore": row.game_score,
        "gameScorePer60": row.game_score_per_60,
        "hockeyValue": row.hockey_value,
        "projectedNextSeasonHockeyValue": row.projected_hockey_value,
        "capHitCents": row.cap_hit_cents,
    }


def contract_season_data(row: ContractSeasonRow) -> ContractSeasonData:
    return {
        "season": row.season_start_year,
        "owningTeam": player_team_data(row),
        "baseSalaryCents": row.base_salary_cents,
        "signingBonusCents": row.signing_bonus_cents,
        "performanceBonusCents": row.performance_bonus_cents,
        "totalCashCents": row.total_cash_cents,
        "capHitCents": row.cap_hit_cents,
        "capPercentage": float(row.cap_percentage)
        if row.cap_percentage is not None
        else None,
        "isSlide": row.is_slide,
    }


def player_team_data(
    row: IdentityRow | SummaryRow | ContractSeasonRow,
) -> TeamSummaryData | None:
    if row.team_id is None:
        return None
    return {
        "id": row.team_id,
        "nhlTeamId": row.nhl_team_id,
        "abbreviation": row.abbreviation,
        "name": row.team_name,
        "city": row.team_city,
        "active": row.team_active,
    }


def team_data(row: TeamRow) -> TeamSummaryData:
    return {
        "id": row.id,
        "nhlTeamId": row.nhl_team_id,
        "abbreviation": row.abbreviation,
        "name": row.team_name,
        "city": row.team_city,
        "active": row.team_active,
    }


def top_summaries(
    skaters: list[PlayerSummaryData], field: str
) -> list[PlayerSummaryData]:
    rows = (
        (value, row["id"], row)
        for row in skaters
        if isinstance(value := row.get(field), (int, float))
    )
    return [row for _, _, row in sorted(rows, key=ranking_key)[:5]]


def ranking_key(
    item: tuple[int | float, int, PlayerSummaryData],
) -> tuple[int | float, int]:
    return -item[0], item[1]

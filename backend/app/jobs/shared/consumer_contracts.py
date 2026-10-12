"""Internal query-result contracts for the unchanged API and ML consumers.

These are projection shapes, not storage models or public response schemas.
Every column must be present, even when its value is null. Query adapters select
an approved source before aggregation; the logical records retain each source.
"""

from datetime import date
from types import MappingProxyType
from typing import Any, Literal, Mapping

from pydantic import StrictBool, StrictInt, create_model

from .data_contracts import Count, Id, Money, Number, Position, Quantity, Ratio, Record, RosterStatus, Season, Seconds, Text


TEAM_COLUMNS = {
    "nhl_team_id": Id | None, "abbreviation": Text, "team_name": Text,
    "team_city": Text | None, "team_active": StrictBool,
}
JOINED_TEAM = {"team_id": Id | None, **{name: kind | None for name, kind in TEAM_COLUMNS.items()}}
IDENTITY_COLUMNS = {
    "id": Id, "first_name": Text, "last_name": Text, "full_name": Text,
    "birth_date": date | None, "age": Count | None, "primary_position": Position | None,
    "shoots_catches": Literal["L", "R"] | None, "nationality": Text | None,
    "active": StrictBool, "roster_status": RosterStatus, **JOINED_TEAM,
}
TRADITIONAL = {name: Count | None for name in (
    "games_played", "goals", "assists", "points", "penalty_minutes", "power_play_goals",
    "power_play_points", "short_handed_goals", "shots",
)} | {"plus_minus": StrictInt | None, "shooting_percentage": Ratio | None}
ADVANCED = {name: Count | None for name in (
    "shifts", "takeaways", "giveaways", "shots_blocked", "penalties", "penalties_drawn",
)} | {
    "ice_time_seconds": Seconds | None, "game_score": Number | None,
    "game_score_per_60": Number | None, "individual_expected_goals": Quantity | None,
    "expected_goals_per_60": Quantity | None, "on_ice_expected_goals_pct": Ratio | None,
}
VALUE_COLUMNS = {
    "hockey_value": Number | None, "projected_hockey_value": Number | None,
    "gs60_above_replacement": Number | None, "model_version": Text | None,
    "cap_hit_cents": Money | None,
}
SUMMARY_COLUMNS = {**IDENTITY_COLUMNS, "season": Season, **TRADITIONAL, **ADVANCED, **VALUE_COLUMNS}
CONTRACT_COLUMNS = {
    "id": Id, "player_id": Id, "signed_on": date | None, "start_season": Season,
    "end_season": Season, "term_years": Id, "contract_type": Text | None,
    "expiry_status": Literal["RFA", "UFA"] | None, "total_value_cents": Money | None,
    "average_value_cents": Money | None, "is_entry_level": StrictBool,
    "signing_team_id": Id | None,
    **{f"signing_{name}": kind | None for name, kind in TEAM_COLUMNS.items()},
}
CONTRACT_SEASON_COLUMNS = {
    "season_start_year": Season, "base_salary_cents": Money | None,
    "signing_bonus_cents": Money | None, "performance_bonus_cents": Money | None,
    "total_cash_cents": Money | None, "cap_hit_cents": Money,
    "cap_percentage": Ratio | None, "is_slide": StrictBool, **JOINED_TEAM,
}
GOALIE_COLUMNS = {name: Count | None for name in (
    "games_played", "wins", "losses", "overtime_losses", "shots_against", "saves",
    "goals_against", "shutouts",
)} | {
    "time_on_ice_seconds": Seconds | None, "save_percentage": Ratio | None,
    "gaa": Quantity | None, "xga": Quantity | None, "ga": Quantity | None,
    "gsae": Number | None,
}
ML_PLAYER_COLUMNS = {
    "player_id": Id, "first_name": Text, "last_name": Text, "player_name": Text,
    "birth_date": date | None, "position": Literal["C", "LW", "RW", "D", "F"] | None,
    "season": Season, "age": Count | None, **TRADITIONAL,
    **{name: kind for name, kind in ADVANCED.items() if name not in {"game_score_per_60", "expected_goals_per_60"}},
    **{name: Count | None for name in (
        "individual_points", "individual_goals", "individual_primary_assists",
        "individual_secondary_assists", "individual_shots_on_goal", "individual_unblocked_attempts",
        "offensive_zone_shift_starts", "defensive_zone_shift_starts", "neutral_zone_shift_starts",
    )},
}


def _projection(name: str, columns: Mapping[str, Any]) -> type[Record]:
    return create_model(name, __base__=Record, **{key: (kind, ...) for key, kind in columns.items()})


QUERY_CONTRACTS: Mapping[str, type[Record]] = MappingProxyType({
    "player_identity": _projection("PlayerIdentityRow", IDENTITY_COLUMNS),
    "player_summary": _projection("PlayerSummaryRow", SUMMARY_COLUMNS),
    "team": _projection("TeamRow", {"id": Id, **TEAM_COLUMNS}),
    "contract": _projection("ContractRow", CONTRACT_COLUMNS),
    "contract_season": _projection("ContractSeasonRow", CONTRACT_SEASON_COLUMNS),
    "goalie_stats": _projection("GoalieStatsRow", GOALIE_COLUMNS),
    "season": _projection("SeasonRow", {"start_year": Season, "end_year": Season, "label": Text, "salary_cap_cents": Money | None}),
    "roster_count": _projection("RosterCountRow", {"roster_status": RosterStatus, "count": Count}),
    "team_cap": _projection("TeamCapRow", {"salary_cap_cents": Money | None, **{name: Money for name in ("active_cap", "ltir_cap", "minors_cap", "total_cap")}}),
    "player_id": _projection("PlayerIdRow", {"id": Id}),
    "contract_player_id": _projection("ContractPlayerIdRow", {"player_id": Id}),
    "history_season": _projection("HistorySeasonRow", {"season": Season}),
    "count": _projection("CountResult", {"value": Count}),
    "exists": _projection("ExistsResult", {"value": StrictBool}),
    "current_season": _projection("CurrentSeasonResult", {"value": Season | None}),
    "health": _projection("HealthResult", {"value": Literal[1]}),
    "ml_player_season": _projection("MLPlayerSeasonRow", ML_PLAYER_COLUMNS),
    "ml_salary_cap": _projection("MLSalaryCapRow", {"season": Season, "end_year": Season, "season_label": Text, "salary_cap_cents": Money, "salary_cap_dollars": Quantity}),
})

# Endpoint paths are relative to the existing API router. Shared projections are
# listed once here; composition and public behavior stay in the current service.
ENDPOINT_QUERIES: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "/health": ("health",),
    "/seasons": ("season", "current_season"),
    "/players": ("player_summary", "count", "exists"),
    "/players/compare": ("player_identity", "player_summary", "goalie_stats", "contract", "contract_season", "exists"),
    "/players/{player_id}": ("player_identity",),
    "/players/{player_id}/stats": ("player_identity", "player_summary", "goalie_stats", "exists"),
    "/players/{player_id}/seasons": ("player_identity", "history_season", "player_summary"),
    "/players/{player_id}/value/history": ("player_identity", "history_season", "player_summary"),
    "/players/{player_id}/value": ("player_identity", "player_summary", "exists", "current_season"),
    "/players/{player_id}/contract": ("player_identity", "contract", "contract_season", "current_season"),
    "/rankings/hockey-value": ("player_summary", "exists"),
    "/teams": ("team",),
    "/teams/{team_id}": ("team", "roster_count"),
    "/teams/{team_id}/roster": ("team", "player_summary", "exists"),
    "/teams/{team_id}/contracts": ("team", "contract_player_id", "player_identity", "contract", "contract_season", "current_season", "exists"),
    "/teams/{team_id}/cap": ("team", "team_cap", "exists"),
    "/search": ("player_id", "player_identity", "team"),
    "/overview": ("player_summary", "exists"),
})


def validate_query_row(query: str, row: Mapping[str, Any]) -> Record:
    """Validate a complete projection without changing its consumer."""
    return QUERY_CONTRACTS[query].model_validate(row)

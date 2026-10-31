"""Reusable immutable API scenarios."""

from dataclasses import asdict
from datetime import date

import pytest
from pydantic import TypeAdapter

from app.api.domain import (
    ContractRow,
    ContractSeasonRow,
    IdentityRow,
    SeasonRow,
    SummaryRow,
    TeamRow,
    CapRow,
)
from app.api.service import TradeValueService
from app.api.tests.fakes import MemoryApiRepository


@pytest.fixture
def summary():
    return SummaryRow(
        id=7,
        first_name="Test",
        last_name="Skater",
        full_name="Test Skater",
        birth_date=date(2000, 1, 1),
        age=26,
        primary_position="C",
        shoots_catches="L",
        nationality="CAN",
        active=True,
        roster_status="ACTIVE",
        team_id=10,
        nhl_team_id=20,
        abbreviation="TST",
        team_name="Testers",
        team_city="Test City",
        team_active=True,
        season=2025,
        games_played=82,
        goals=30,
        assists=50,
        points=80,
        plus_minus=10,
        penalty_minutes=20,
        power_play_goals=8,
        power_play_points=20,
        short_handed_goals=1,
        shots=200,
        shooting_percentage=0.15,
        ice_time_seconds=3600.4,
        shifts=100,
        game_score=2.0,
        game_score_per_60=2.0,
        individual_expected_goals=18.5,
        expected_goals_per_60=1.1,
        on_ice_expected_goals_pct=0.55,
        takeaways=12,
        giveaways=8,
        shots_blocked=6,
        penalties=5,
        penalties_drawn=9,
        hockey_value=1.5,
        projected_hockey_value=2.25,
        gs60_above_replacement=1.5,
        model_version="test-v1",
        cap_hit_cents=800000000,
    )


@pytest.fixture
def repository(summary, contract_row, contract_season):
    identity = TypeAdapter(IdentityRow).validate_python(asdict(summary))
    team = TeamRow(
        id=10,
        nhl_team_id=20,
        abbreviation="TST",
        team_name="Testers",
        team_city="Test City",
        team_active=True,
    )
    season = SeasonRow(
        start_year=2025, end_year=2026, label="2025-26", salary_cap_cents=9_550_000_000
    )
    cap = CapRow(
        salary_cap_cents=9_550_000_000,
        active_cap=800_000_000,
        ltir_cap=200_000_000,
        minors_cap=100_000_000,
        total_cap=1_100_000_000,
    )
    return MemoryApiRepository(
        season_rows=(season,),
        player_rows=(identity,),
        team_rows=(team,),
        summaries=(summary,),
        contract_rows=(contract_row,),
        contract_season_rows=((30, contract_season),),
        cap_rows=((10, 2025, cap),),
    )


@pytest.fixture
def service(repository):
    return TradeValueService(repository=repository, as_of=date(2026, 6, 30))


@pytest.fixture
def contract_row():
    return ContractRow(
        id=30,
        player_id=7,
        signing_team_id=10,
        signing_nhl_team_id=20,
        signing_abbreviation="TST",
        signing_team_name="Testers",
        signing_team_city="Test City",
        signing_team_active=True,
        signed_on=date(2025, 7, 1),
        start_season=2025,
        end_season=2026,
        term_years=2,
        contract_type="STANDARD",
        expiry_status="UFA",
        total_value_cents=1600000000,
        average_value_cents=800000000,
        is_entry_level=False,
    )


@pytest.fixture
def contract_season():
    return ContractSeasonRow(
        team_id=10,
        nhl_team_id=20,
        abbreviation="TST",
        team_name="Testers",
        team_city="Test City",
        team_active=True,
        season_start_year=2025,
        base_salary_cents=700000000,
        signing_bonus_cents=100000000,
        performance_bonus_cents=None,
        total_cash_cents=800000000,
        cap_hit_cents=800000000,
        cap_percentage=0.08376963,
        is_slide=False,
    )

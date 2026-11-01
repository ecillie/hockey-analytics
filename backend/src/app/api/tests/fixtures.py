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
from sqlalchemy import text
from app.config import AppEnvironment, DatabaseSettings
from app.database import open_database_resources
from sqlalchemy.orm import Session
from app.api.repository import SqlApiRepository


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


SEED_SQL = r"""
TRUNCATE teams, players, model_versions RESTART IDENTITY CASCADE;

INSERT INTO teams (id, nhl_team_id, abbreviation, name, city, active) VALUES
    (101, 1, 'AAA', 'Alphas', 'Alpha City', TRUE),
    (102, 2, 'BBB', 'Betas', 'Beta City', TRUE),
    (103, 3, 'OLD', 'Old Team', 'Old City', FALSE);

INSERT INTO players (id, first_name, last_name, birth_date, primary_position, shoots_catches, nationality, active, roster_status) VALUES
    (1001, 'Traded', 'Star', '1998-01-01', 'C', 'L', 'CAN', TRUE, 'ACTIVE'),
    (1002, 'Low', 'Forward', '1999-02-02', 'LW', 'L', 'USA', TRUE, 'ACTIVE'),
    (1003, 'Mid', 'Forward', '2000-03-03', 'RW', 'R', 'SWE', TRUE, 'LTIR'),
    (1004, 'High', 'Forward', '2001-04-04', 'C', 'R', 'FIN', TRUE, 'ACTIVE'),
    (1005, 'Test', 'Defender', '1997-05-05', 'D', 'L', 'CAN', TRUE, 'ACTIVE'),
    (1006, 'Goal', 'Tender', '1996-06-06', 'G', 'L', 'CZE', TRUE, 'MINORS'),
    (1007, 'No', 'Data', NULL, 'F', NULL, NULL, FALSE, 'UNKNOWN');

INSERT INTO player_team_stints (player_id, season_start_year, team_id, joined_on, departed_on) VALUES
    (1001, 2025, 101, '2025-07-01', '2026-01-01'),
    (1001, 2025, 102, '2026-01-02', NULL),
    (1002, 2025, 101, '2025-07-01', '2026-02-01'),
    (1002, 2025, 102, '2026-02-02', NULL),
    (1003, 2025, 102, '2025-07-01', NULL),
    (1004, 2025, 102, '2025-07-01', NULL),
    (1005, 2025, 101, '2025-07-01', NULL),
    (1006, 2025, 101, '2025-07-01', NULL);

INSERT INTO skater_season_stats
    (player_id, season_start_year, team_id, stat_scope, game_type, source_id,
     games_played, goals, assists, points, plus_minus, penalty_minutes,
     power_play_goals, power_play_points, short_handed_goals, shots)
VALUES
    (1001, 2025, 101, 'TEAM', 2, 1, 40, 10, 15, 25, 2, 8, 2, 5, 0, 80),
    (1001, 2025, 102, 'TEAM', 2, 1, 42, 20, 35, 55, 8, 12, 6, 15, 1, 120),
    (1001, 2025, NULL, 'TOTAL', 2, 1, 82, 30, 50, 80, 10, 20, 8, 20, 1, 200),
    (1002, 2025, 101, 'TEAM', 2, 1, 8, 1, 1, 2, -3, 2, 0, 0, 0, 8),
    (1002, 2025, 102, 'TEAM', 2, 1, 12, 1, 2, 3, -2, 2, 0, 0, 0, 12),
    (1003, 2025, NULL, 'TOTAL', 2, 1, 40, 10, 20, 30, 1, 6, 2, 8, 0, 100),
    (1004, 2025, NULL, 'TOTAL', 2, 1, 50, 25, 35, 60, 12, 10, 7, 18, 1, 180),
    (1005, 2025, NULL, 'TOTAL', 2, 1, 30, 5, 20, 25, 4, 14, 1, 7, 0, 90);

INSERT INTO skater_advanced_season_stats
    (player_id, season_start_year, team_id, stat_scope, game_type, situation,
     source_id, games_played, ice_time_seconds, shifts, game_score,
     individual_expected_goals, on_ice_expected_goals_pct, shots_blocked,
     takeaways, giveaways, penalties, penalties_drawn)
VALUES
    (1001, 2025, 101, 'TEAM', 2, 'all', 2, 40, 48000, 400, 26.6666667, 7, 0.51, 10, 8, 5, 3, 4),
    (1001, 2025, 102, 'TEAM', 2, 'all', 2, 42, 50400, 450, 28.0, 11, 0.57, 12, 10, 7, 4, 6),
    (1001, 2025, NULL, 'TOTAL', 2, 'all', 2, 82, 98400, 850, 54.6666667, 18, 0.55, 22, 18, 12, 7, 10),
    (1002, 2025, 101, 'TEAM', 2, 'all', 2, 8, 4800, 30, 0.6666667, 0.4, 0.39, 1, 0, 1, 1, 0),
    (1002, 2025, 102, 'TEAM', 2, 'all', 2, 12, 7200, 50, 1.0, 0.6, 0.41, 1, 1, 2, 1, 1),
    (1003, 2025, NULL, 'TOTAL', 2, 'all', 2, 40, 36000, 500, 15.0, 10, 0.50, 15, 12, 10, 5, 5),
    (1004, 2025, NULL, 'TOTAL', 2, 'all', 2, 50, 60000, 700, 60.0, 25, 0.60, 18, 20, 9, 6, 12),
    (1005, 2025, NULL, 'TOTAL', 2, 'all', 2, 30, 33000, 300, 11.0, 4, 0.52, 40, 8, 6, 4, 3);

INSERT INTO goalie_season_stats
    (player_id, season_start_year, team_id, stat_scope, game_type, source_id,
     games_played, wins, losses, overtime_losses, shots_against, saves,
     goals_against, shutouts, time_on_ice_seconds)
VALUES
    (1006, 2025, 101, 'TEAM', 2, 1, 10, 5, 4, 1, 300, 275, 25, 1, 36000),
    (1006, 2025, 102, 'TEAM', 2, 1, 12, 7, 4, 1, 360, 330, 30, 1, 43200),
    (1006, 2025, NULL, 'TOTAL', 2, 1, 22, 12, 8, 2, 660, 605, 55, 2, 79200);

INSERT INTO goalie_advanced_season_stats
    (player_id, season_start_year, team_id, stat_scope, game_type, situation,
     source_id, games_played, ice_time_seconds, expected_goals_against, goals_against)
VALUES
    (1006, 2025, NULL, 'TOTAL', 2, 'all', 2, 22, 79200, 60, 55);

INSERT INTO contracts
    (id, player_id, signing_team_id, source_id, external_id, signed_on,
     start_season, end_season, term_years, contract_type, expiry_status,
     total_value_cents, average_value_cents, is_entry_level)
VALUES
    (2001, 1001, 101, 3, 'contract-1', '2025-07-01', 2025, 2026, 2, 'STANDARD', 'UFA', 1600000000, 800000000, FALSE),
    (2002, 1003, 102, 3, 'contract-2', '2025-07-01', 2025, 2025, 1, 'STANDARD', 'RFA', 200000000, 200000000, FALSE),
    (2003, 1006, 101, 3, 'contract-3', '2025-07-01', 2025, 2025, 1, 'ONE_WAY', 'RFA', 100000000, 100000000, FALSE);

INSERT INTO contract_seasons
    (contract_id, season_start_year, owning_team_id, base_salary_cents,
     signing_bonus_cents, performance_bonus_cents, total_cash_cents,
     cap_hit_cents, cap_percentage, is_slide)
VALUES
    (2001, 2025, 102, 700000000, 100000000, 0, 800000000, 800000000, 0.08376963, FALSE),
    (2001, 2026, 102, 800000000, 0, 0, 800000000, 800000000, 0.07692308, FALSE),
    (2002, 2025, 102, 200000000, 0, 0, 200000000, 200000000, 0.02094241, FALSE),
    (2003, 2025, 101, 100000000, 0, 0, 100000000, 100000000, 0.01047120, FALSE);

INSERT INTO model_versions
    (id, model_type, version, artifact_uri, feature_schema,
     training_start_season, training_end_season, active)
VALUES
    (3001, 'skater_value', 'integration-v1', 'memory://integration', '{}', 2024, 2025, TRUE);

INSERT INTO predictions
    (model_version_id, player_id, target_season, position_group,
     predicted_aav_cents, input_features)
VALUES
    (3001, 1001, 2026, 'forward', 800000000, '{"predicted_hockey_value": 42.5}');
"""


@pytest.fixture(scope="module")
def postgres_api_engine(disposable_database_url):
    settings = DatabaseSettings(
        environment=AppEnvironment.DEV, database_url=disposable_database_url
    )
    with open_database_resources(settings) as resources:
        database_engine = resources.engine
        with database_engine.begin() as connection:
            assert (
                connection.execute(
                    text("SELECT to_regclass('public.players')")
                ).scalar_one()
                == "players"
            )
            connection.exec_driver_sql(SEED_SQL)
        yield database_engine


@pytest.fixture()
def postgres_api_service(postgres_api_engine):
    with Session(postgres_api_engine) as session:
        yield TradeValueService(repository=SqlApiRepository(session=session))

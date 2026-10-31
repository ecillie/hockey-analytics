"""Fixture-shaped payloads for typed source ingestion tests."""

import pytest
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.domain import (
    MoneyPuckOptions,
)


@pytest.fixture
def source_puck_options(tmp_path):
    skater = tmp_path.joinpath("skaters.csv")
    goalie = tmp_path.joinpath("goalies.csv")
    skater.write_text(
        "playerId,season,name,team,position,situation,games_played,icetime,gameScore\n1,2024,Test Skater,AAA,C,all,10,1200,2.5\n"
    )
    goalie.write_text(
        "playerId,season,name,team,position,situation,games_played,icetime,xGoals\n2,2024,Test Goalie,BBB,G,all,8,1000,12.5\n"
    )
    return MoneyPuckOptions(
        skater_file=skater,
        goalie_file=goalie,
        expected_seasons=(2024, 2025),
        minimum_rows_per_kind=2,
        maximum_duplicate_ratio=0.5,
    )


@pytest.fixture
def source_puck_csv():
    return {
        "https://moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/skaters.csv": "playerId,season,name,team,position,situation,games_played,icetime,gameScore\n1,2025,Test Skater,AAA,C,all,12,1300,4.5\n1,2025,Test Skater,AAA,C,all,15,1500,6.5\n",
        "https://moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/goalies.csv": "playerId,season,name,team,position,situation,games_played,icetime,xGoals\n2,2025,Test Goalie,BBB,G,all,10,1300,14.5\n",
    }


@pytest.fixture
def source_stat_row():
    return {
        "playerId": 1,
        "skaterFullName": "Test Skater",
        "goalieFullName": "Test Goalie",
        "teamAbbrevs": "AAA,BBB",
        "gamesPlayed": 10,
        "goals": 5,
        "assists": 7,
        "points": 12,
        "shotsAgainst": 100,
        "saves": 95,
        "goalsAgainst": 5,
    }


@pytest.fixture
def source_schedule_page():
    return {
        "gameWeek": [
            {
                "date": "2025-10-01",
                "games": [
                    {
                        "id": 1,
                        "gameType": 2,
                        "awayTeam": {"abbrev": "AAA", "score": 2},
                        "homeTeam": {"abbrev": "BBB", "score": 3},
                        "gameState": "FINAL",
                    }
                ],
            }
        ],
        "nextStartDate": None,
    }

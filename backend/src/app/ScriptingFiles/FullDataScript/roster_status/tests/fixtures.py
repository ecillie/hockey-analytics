"""Shared roster scenarios and feed-shaped payloads."""

from datetime import date
import pytest

from app.ScriptingFiles.FullDataScript.roster_status.domain import (
    ExternalRosterPlayer,
    StoredPlayer,
    RosterStatus,
)


@pytest.fixture
def player():
    return StoredPlayer(
        id=1,
        first_name="Kaapo",
        last_name="Kahkonen",
        birth_date=date(1996, 8, 16),
        roster_status=RosterStatus.ACTIVE,
        nhl_external_id="11",
    )


@pytest.fixture
def ahl_player():
    return ExternalRosterPlayer(
        external_id="7179", full_name="Kaapo Kähkönen", birth_date=date(1996, 8, 16)
    )


@pytest.fixture
def nhl_payloads():
    return {
        "https://api-web.nhle.com/v1/standings/now": {
            "standings": [
                {"teamAbbrev": {"default": "EDM"}},
                {"teamAbbrev": {"default": "TOR"}},
            ]
        },
        "https://api-web.nhle.com/v1/roster/EDM/current": {
            "forwards": [
                {
                    "id": 11,
                    "firstName": {"default": "NHL"},
                    "lastName": {"default": "Player"},
                }
            ],
            "defensemen": [],
            "goalies": [],
        },
        "https://api-web.nhle.com/v1/roster/TOR/current": {
            "forwards": [],
            "defensemen": [],
            "goalies": [],
        },
    }


@pytest.fixture
def ahl_payloads():
    return {
        "bootstrap": {
            "current_season_id": "90",
            "current_league_id": "4",
            "teamsNoAll": [{"id": "415"}, {"id": "416"}],
        },
        "415": {
            "roster": [
                {
                    "sections": [
                        {
                            "data": [
                                {
                                    "row": {
                                        "player_id": "7179",
                                        "name": "Kaapo Kähkönen",
                                        "birthdate": "1996-08-16",
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        },
        "416": {"roster": []},
    }

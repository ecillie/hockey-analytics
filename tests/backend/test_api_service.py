"""API orchestration behavior against an in-memory repository."""

from dataclasses import replace
from datetime import date

import pytest

from app.api.domain import GoalieRow
from app.api.errors import ApiProblem
from app.api.policy import buried_relief_cents, latest_started_season
from app.api.repository import ApiRepository
from app.api.service import TradeValueService
from app.api.tests.fakes import MemoryApiRepository
from app.api.util import identity_data, summary_data


class TestSeasonPolicy:
    @pytest.mark.parametrize(
        ("season", "expected"),
        [
            pytest.param(2012, 0, id="before-buried-relief"),
            pytest.param(2013, 92_500_000, id="2013-minimum"),
            pytest.param(2015, 95_000_000, id="2015-minimum"),
            pytest.param(2017, 102_500_000, id="2017-minimum"),
            pytest.param(2019, 107_500_000, id="2019-minimum"),
            pytest.param(2021, 112_500_000, id="2021-minimum"),
            pytest.param(2025, 115_000_000, id="2025-minimum"),
            pytest.param(2026, 122_500_000, id="2026-minimum"),
        ],
    )
    def test_buried_relief(self, season, expected):
        assert buried_relief_cents(season) == expected

    @pytest.mark.parametrize(
        ("as_of", "expected"),
        [
            pytest.param(date(2026, 1, 1), 2025, id="january"),
            pytest.param(date(2026, 6, 30), 2025, id="before-cutoff"),
            pytest.param(date(2026, 7, 1), 2026, id="cutoff"),
            pytest.param(date(2026, 12, 31), 2026, id="december"),
        ],
    )
    def test_visibility(self, as_of, expected):
        assert latest_started_season(as_of) == expected


class TestConfiguredSeasons:
    def test_default_and_list_use_the_same_visibility(self, service):
        result = service.seasons()
        assert result["currentSeason"] == 2025
        assert [r["startYear"] for r in result["availableSeasons"]] == [2025]
        service.require_season(2025)

    def test_unknown_season_retains_public_error_and_typed_context(self, service):
        with pytest.raises(ApiProblem) as failure:
            service.require_season(2099)
        assert (failure.value.status, failure.value.code, failure.value.details) == (
            400,
            "INVALID_SEASON",
            {"season": ["Unknown season."]},
        )

    @pytest.fixture
    def empty_service(self):
        return TradeValueService(repository=MemoryApiRepository())

    def test_no_configured_seasons(self, empty_service):
        with pytest.raises(ApiProblem) as failure:
            empty_service.current_season()
        assert (failure.value.status, failure.value.code) == (
            503,
            "SEASONS_UNAVAILABLE",
        )


class TestIdentityAndListing:
    @pytest.fixture
    def nullable(self, summary):
        return replace(summary, team_id=None, ice_time_seconds=10.6, goals=None)

    def test_nulls_and_rounding(self, nullable):
        assert identity_data(nullable)["team"] is None
        result = summary_data(nullable)
        assert result["toiSeconds"] == 11
        assert result["goals"] is None

    def test_missing_entities(self, service):
        with pytest.raises(ApiProblem, match="Player not found"):
            service.player_identity(999)
        with pytest.raises(ApiProblem, match="Team not found"):
            service.team_summary(999)

    def test_repository_protocol_and_health(self, service):
        assert isinstance(service.repository, ApiRepository)
        service.check_health()

    def test_players_filter_and_paginate(self, service):
        result = service.players(
            2025, "tst", "C", "ACTIVE", " Test ", "points", "asc", 1, 2
        )
        assert result["pagination"] == {
            "page": 1,
            "pageSize": 2,
            "totalItems": 1,
            "totalPages": 1,
        }
        assert result["data"][0]["fullName"] == "Test Skater"

    def test_teams_counts_and_roster(self, service):
        assert service.teams()[0]["id"] == 10
        assert service.team(10)["rosterCounts"] == {
            "ACTIVE": 1,
            "MINORS": 0,
            "LTIR": 0,
            "UNKNOWN": 0,
        }
        assert service.roster(10, 2025, "ACTIVE")["players"][0]["id"] == 7


class TestStats:
    @pytest.fixture
    def missing_summary(self, repository):
        return TradeValueService(repository=replace(repository, summaries=()))

    @pytest.fixture
    def no_stats(self, repository, summary):
        return TradeValueService(
            repository=replace(
                repository,
                summaries=(replace(summary, games_played=None, ice_time_seconds=None),),
            )
        )

    @pytest.fixture
    def goalie_row(self):
        return GoalieRow(
            games_played=20,
            wins=12,
            losses=6,
            overtime_losses=2,
            shots_against=600,
            saves=550,
            save_percentage=550 / 600,
            goals_against=50,
            time_on_ice_seconds=72_000,
            gaa=2.5,
            shutouts=2,
            xga=55.0,
            ga=50.0,
            gsae=5.0,
        )

    @pytest.fixture(
        params=[
            pytest.param("present", id="goalie-stats"),
            pytest.param("empty", id="empty-aggregate"),
            pytest.param("absent", id="missing-aggregate"),
        ]
    )
    def goalie_service(self, request, repository, summary, goalie_row):
        row = replace(summary, primary_position="G")
        stats = (
            ()
            if request.param == "absent"
            else (
                (
                    7,
                    2025,
                    goalie_row
                    if request.param == "present"
                    else replace(goalie_row, games_played=None),
                ),
            )
        )
        return TradeValueService(
            repository=replace(repository, summaries=(row,), goalie_rows=stats)
        ), request.param

    def test_skater(self, service):
        result = service.player_stats(7, 2025)
        assert result["traditional"] is not None
        assert result["traditional"]["shootingPercentage"] == 0.15
        assert result["advanced"] is not None
        assert result["advanced"]["iceTimeSeconds"] == 3600
        assert result["goalie"] is None

    def test_goalie_and_missing_goalie_stats(self, goalie_service):
        service, scenario = goalie_service
        result = service.player_stats(7, 2025)
        assert result["traditional"] is None
        assert result["advanced"] is None
        if scenario == "present":
            assert result["goalie"]["goalsSavedAboveExpected"] == 5.0
        if scenario != "present":
            assert result["goalie"] is None

    def test_missing_skater_stats(self, no_stats):
        result = no_stats.player_stats(7, 2025)
        assert result["traditional"] is None
        assert result["advanced"] is None

    def test_missing_summary(self, missing_summary):
        with pytest.raises(ApiProblem, match="Player not found"):
            missing_summary.player_stats(7, 2025)


class TestValueAndHistory:
    @pytest.fixture
    def missing_history(self, repository):
        return TradeValueService(
            repository=replace(repository, summaries=(), missing_history=(2024,))
        )

    def test_value_and_history(self, service):
        assert service.hockey_value(7, None) == {
            "playerId": 7,
            "season": 2025,
            "hockeyValue": 1.5,
            "projectedNextSeasonHockeyValue": 2.25,
            "gameScorePer60AboveReplacement": 1.5,
            "toiHours": pytest.approx(1.000111),
            "modelVersion": "test-v1",
        }
        assert service.player_seasons(7)[0]["season"] == 2025
        assert service.value_history(7) == [{"season": 2025, "hockeyValue": 1.5}]
        assert service.leaders(2025, "C", "TST", 5)[0]["id"] == 7
        assert service.leaders(2025, None, None, 5)[0]["id"] == 7

    def test_missing_summary_history_is_omitted_and_value_is_null(
        self, missing_history
    ):
        assert missing_history.player_seasons(7) == []
        result = missing_history.hockey_value(7, 2025)
        assert result["hockeyValue"] is None
        assert result["toiHours"] is None


class TestContractsAndCap:
    @pytest.fixture
    def unsigned(self, repository, contract_row):
        return TradeValueService(
            repository=replace(
                repository,
                contract_rows=(replace(contract_row, signing_team_id=None),),
                contract_season_rows=(),
            )
        )

    @pytest.fixture(
        params=[
            pytest.param("null-ceiling", id="null-ceiling"),
            pytest.param("absent", id="absent-cap"),
        ]
    )
    def cap_service(self, request, repository):
        cap = repository.cap_rows[0][2]
        rows = (
            ()
            if request.param == "absent"
            else ((10, 2025, replace(cap, salary_cap_cents=None)),)
        )
        return TradeValueService(
            repository=replace(repository, cap_rows=rows)
        ), request.param

    @pytest.fixture
    def unmatched_contract(self, repository, contract_row, contract_season):
        row = replace(contract_season, season_start_year=2024)
        return TradeValueService(
            repository=replace(
                repository,
                contract_season_rows=((30, row),),
                contract_player_rows=((10, 2025, 7),),
            )
        )

    @pytest.fixture
    def no_contract(self, repository):
        return TradeValueService(
            repository=replace(
                repository, contract_rows=(), contract_player_rows=((10, 2025, 7),)
            )
        )

    def test_contract_and_team_contracts(self, service):
        result = service.contract(7)
        assert result is not None
        assert result["signingTeam"] is not None
        assert result["signingTeam"]["id"] == 10
        assert result["seasons"][0]["capPercentage"] == pytest.approx(0.08376963)
        assert (
            service.team_contracts(10, 2025)["contracts"][0]["season"]["capHitCents"]
            == 800_000_000
        )

    def test_contract_without_signing_team(self, unsigned):
        result = unsigned.contract(7, 2025)
        assert result is not None
        assert result["signingTeam"] is None
        assert result["seasons"] == []

    def test_no_contract(self, no_contract):
        assert no_contract.contract(7, 2025) is None
        assert no_contract.team_contracts(10, 2025)["contracts"] == []

    def test_unmatched_contract_season(self, unmatched_contract):
        assert unmatched_contract.team_contracts(10, 2025)["contracts"] == []

    def test_estimated_cap(self, service):
        result = service.team_cap(10, 2025)
        assert result["capSpaceCents"] == 8_750_000_000
        assert result["calculationStatus"] == "ESTIMATE"

    def test_missing_and_null_cap(self, cap_service):
        service, scenario = cap_service
        if scenario == "absent":
            with pytest.raises(ApiProblem) as failure:
                service.team_cap(10, 2025)
            assert (failure.value.status, failure.value.code) == (
                503,
                "SEASONS_UNAVAILABLE",
            )
            return
        assert service.team_cap(10, 2025)["capSpaceCents"] is None


class TestOverviewSearchAndCompare:
    @pytest.fixture
    def overview(self, repository, summary):
        goalie = replace(
            summary,
            id=8,
            primary_position="G",
            goals=None,
            points=None,
            hockey_value=None,
        )
        return TradeValueService(
            repository=replace(repository, summaries=(summary, goalie))
        )

    @pytest.fixture
    def empty_overview(self, repository):
        return TradeValueService(repository=replace(repository, summaries=()))

    def test_overview(self, overview):
        result = overview.overview(2025)
        assert result["league"] == {
            "players": 2,
            "goals": 30,
            "gamesPlayed": 164,
            "averageHockeyValue": 1.5,
        }
        assert result["leaders"]["points"][0]["id"] == 7

    def test_empty_overview(self, empty_overview):
        assert empty_overview.overview(2025)["league"]["averageHockeyValue"] is None

    def test_search(self, service):
        assert service.search("Test", ["player"], 8)["players"][0]["id"] == 7
        assert service.search("Test", ["team"], 8)["teams"][0]["id"] == 10
        result = service.search("Test", ["player", "team"], 8)
        assert len(result["players"]) == len(result["teams"]) == 1

    def test_compare(self, service):
        result = service.compare([7], 2025)
        assert result["players"][0]["player"]["id"] == 7
        assert result["players"][0]["stats"]["season"] == 2025
        assert result["players"][0]["contract"] is not None

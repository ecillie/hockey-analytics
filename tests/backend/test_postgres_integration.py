from app.api.tests.fakes import SeasonBoundaryScenario
from app.api.domain import PlayerQuery
from datetime import date
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.api.errors import ApiProblem
from app.api.repository import SqlApiRepository
from app.api.service import TradeValueService


@pytest.mark.integration
def test_listing_prefers_total_rows_and_current_team(
    postgres_api_service, listing_queries
):
    result = postgres_api_service.players(listing_queries[0])
    assert result["pagination"] == {
        "page": 1,
        "pageSize": 3,
        "totalItems": 6,
        "totalPages": 2,
    }
    traded = next(player for player in result["data"] if player["id"] == 1001)
    assert (traded["gamesPlayed"], traded["goals"], traded["points"]) == (82, 30, 80)
    assert traded["team"]["abbreviation"] == "BBB"
    assert traded["hockeyValue"] == pytest.approx(41.0)
    assert traded["projectedNextSeasonHockeyValue"] == pytest.approx(42.5)

    aggregated = postgres_api_service.players(listing_queries[1])["data"][0]
    assert (aggregated["gamesPlayed"], aggregated["goals"], aggregated["points"]) == (
        20,
        2,
        5,
    )
    assert aggregated["team"]["abbreviation"] == "BBB"

    filtered = postgres_api_service.players(listing_queries[2])
    assert [player["id"] for player in filtered["data"]] == [1004]


@pytest.fixture
def listing_queries():
    return (
        PlayerQuery(season=2025, sort="points", page_size=3),
        PlayerQuery(
            season=2025, search="Low Forward", sort="name", order="asc", page_size=10
        ),
        PlayerQuery(
            season=2025,
            team="bbb",
            position="C",
            roster_status="ACTIVE",
            search="High",
            sort="name",
            order="asc",
            page_size=10,
        ),
    )


@pytest.mark.integration
def test_validation_missing_entities_and_nullable_identity(postgres_api_service):
    assert [team["id"] for team in postgres_api_service.teams()] == [101, 102]

    with pytest.raises(ApiProblem) as invalid:
        postgres_api_service.require_season(2099)
    assert (invalid.value.status, invalid.value.code) == (400, "INVALID_SEASON")

    with pytest.raises(ApiProblem) as player_missing:
        postgres_api_service.player_identity(9999)
    assert player_missing.value.code == "PLAYER_NOT_FOUND"

    with pytest.raises(ApiProblem) as team_missing:
        postgres_api_service.team_summary(9999)
    assert team_missing.value.code == "TEAM_NOT_FOUND"

    identity = postgres_api_service.player_identity(1007)
    assert identity["team"] is None
    assert identity["birthDate"] is None
    assert postgres_api_service.contract(1007, 2025) is None
    assert postgres_api_service.hockey_value(1007, 2025) == {
        "playerId": 1007,
        "season": 2025,
        "hockeyValue": None,
        "projectedNextSeasonHockeyValue": None,
        "gameScorePer60AboveReplacement": None,
        "toiHours": None,
        "modelVersion": None,
    }


class TestSeasonCatalogBoundary:
    @pytest.fixture
    def services(self, postgres_api_engine):
        with Session(postgres_api_engine) as session:
            repository = SqlApiRepository(session=session)
            yield SeasonBoundaryScenario(
                before=TradeValueService(
                    repository=repository, as_of=date(2026, 6, 30)
                ),
                on=TradeValueService(repository=repository, as_of=date(2026, 7, 1)),
            )

    @pytest.mark.integration
    def test_season_catalog_and_validation_share_the_july_first_boundary(
        self, services
    ):
        before_info = services.before.seasons()
        assert before_info["currentSeason"] == 2025
        assert max(s["startYear"] for s in before_info["availableSeasons"]) == 2025
        with pytest.raises(ApiProblem) as future:
            services.before.require_season(2026)
        assert future.value.code == "INVALID_SEASON"

        on_cutoff_info = services.on.seasons()
        assert on_cutoff_info["currentSeason"] == 2026
        assert max(s["startYear"] for s in on_cutoff_info["availableSeasons"]) == 2026
        services.on.require_season(2026)


@pytest.mark.integration
def test_skater_goalie_history_and_value(postgres_api_service):
    skater = postgres_api_service.player_stats(1001, 2025)
    assert skater["traditional"]["gamesPlayed"] == 82
    assert skater["advanced"]["iceTimeSeconds"] == 98_400
    assert skater["goalie"] is None

    goalie = postgres_api_service.player_stats(1006, 2025)
    assert goalie["traditional"] is None
    assert goalie["goalie"]["gamesPlayed"] == 22
    assert goalie["goalie"]["goalsSavedAboveExpected"] == pytest.approx(5.0)

    value = postgres_api_service.hockey_value(1001, 2025)
    assert value["gameScorePer60AboveReplacement"] == pytest.approx(1.5)
    assert value["toiHours"] == pytest.approx(27.3333333)
    assert value["modelVersion"] == "integration-v1"
    assert postgres_api_service.value_history(1001) == [
        {"season": 2025, "hockeyValue": pytest.approx(41.0)}
    ]


@pytest.mark.integration
def test_team_roster_contract_and_raw_cap_subtotals(postgres_api_service):
    team = postgres_api_service.team(102)
    assert team["rosterCounts"] == {"ACTIVE": 3, "MINORS": 0, "LTIR": 1, "UNKNOWN": 0}

    roster = postgres_api_service.roster(102, 2025, "ACTIVE")
    assert [player["id"] for player in roster["players"]] == [1004, 1002, 1001]
    assert len(postgres_api_service.roster(102, 2025, None)["players"]) == 4

    contract = postgres_api_service.contract(1001, 2025)
    assert contract["signingTeam"]["abbreviation"] == "AAA"
    assert [season["season"] for season in contract["seasons"]] == [2025, 2026]
    assert contract["seasons"][0]["capHitCents"] == 800_000_000

    contracts = postgres_api_service.team_contracts(102, 2025)
    assert [row["player"]["id"] for row in contracts["contracts"]] == [1001, 1003]

    cap = postgres_api_service.team_cap(102, 2025)
    assert cap["activeRosterCapCents"] == 800_000_000
    assert cap["ltirCapCents"] == 200_000_000
    assert cap["minorsCapCents"] == 0
    assert cap["totalCommitmentsCents"] == 1_000_000_000
    assert cap["calculationStatus"] == "ESTIMATE"


@pytest.mark.integration
def test_search_leaders_overview_and_compare(
    postgres_api_service, combined_types, player_types, comparison_ids
):
    found = postgres_api_service.search("Beta", combined_types, 8)
    assert found["players"] == []
    assert [team["id"] for team in found["teams"]] == [102]
    players_only = postgres_api_service.search("Traded", player_types, 8)
    assert [player["id"] for player in players_only["players"]] == [1001]
    assert players_only["teams"] == []

    leaders = postgres_api_service.leaders(2025, "C", "BBB", 5)
    assert [player["id"] for player in leaders] == [1004, 1001]

    overview = postgres_api_service.overview(2025)
    assert overview["league"]["players"] == 6
    assert overview["league"]["goals"] == 72
    assert overview["leaders"]["hockeyValue"][0]["id"] == 1004

    comparison = postgres_api_service.compare(comparison_ids, 2025)
    assert [row["player"]["id"] for row in comparison["players"]] == [1001, 1006]
    assert comparison["players"][0]["contract"] is not None
    assert comparison["players"][1]["stats"]["goalie"] is not None


@pytest.fixture
def combined_types():
    return ["player", "team"]


@pytest.fixture
def player_types():
    return ["player"]


@pytest.fixture
def comparison_ids():
    return [1001, 1006]


@pytest.mark.integration
def test_known_player_without_season_data_returns_empty_stat_groups(
    postgres_api_service,
):
    stats = postgres_api_service.player_stats(1007, 2025)

    assert stats == {
        "playerId": 1007,
        "season": 2025,
        "team": None,
        "traditional": None,
        "advanced": None,
        "goalie": None,
    }


class TestOnlyTheActiveModelCanSupplyTheCurrentProjection:
    @pytest.fixture
    def scenario(self, postgres_api_service):
        postgres_api_service.repository.session.execute(
            text(
                """INSERT INTO model_versions
                     (id, model_type, version, artifact_uri, feature_schema,
                      training_start_season, training_end_season, active, created_at)
                   VALUES
                     (3002, 'skater_value', 'retired-v2', 'memory://retired', '{}',
                      2024, 2025, FALSE, CURRENT_TIMESTAMP + INTERVAL '1 day')"""
            )
        )
        postgres_api_service.repository.session.execute(
            text(
                """INSERT INTO predictions
                     (model_version_id, player_id, target_season, position_group,
                      predicted_aav_cents, input_features, created_at)
                   VALUES
                     (3002, 1001, 2026, 'forward', 999999999,
                      '{"predicted_hockey_value": 99}',
                      CURRENT_TIMESTAMP + INTERVAL '1 day')"""
            )
        )
        return postgres_api_service

    @pytest.mark.integration
    def test_only_the_active_model_can_supply_the_current_projection(
        self, scenario, postgres_api_service
    ):
        postgres_api_service = scenario
        value = postgres_api_service.hockey_value(1001, 2025)

        assert value["modelVersion"] == "integration-v1"
        assert value["projectedNextSeasonHockeyValue"] == pytest.approx(42.5)


class TestReplacementLevelExcludesPlayersBelowTwentyGames:
    @pytest.fixture
    def scenario(self, postgres_api_service):
        postgres_api_service.repository.session.execute(
            text(
                """INSERT INTO players
                     (id, first_name, last_name, primary_position, active, roster_status)
                   VALUES (1009, 'Short', 'Callup', 'C', TRUE, 'ACTIVE');
                   INSERT INTO player_team_stints
                     (player_id, season_start_year, team_id, joined_on)
                   VALUES (1009, 2025, 101, '2026-03-01');
                   INSERT INTO skater_season_stats
                     (player_id, season_start_year, team_id, stat_scope, game_type,
                      source_id, games_played, goals, assists, points, shots)
                   VALUES (1009, 2025, NULL, 'TOTAL', 2, 1, 19, 0, 0, 0, 10);
                   INSERT INTO skater_advanced_season_stats
                     (player_id, season_start_year, team_id, stat_scope, game_type,
                      situation, source_id, games_played, ice_time_seconds, game_score)
                   VALUES (1009, 2025, NULL, 'TOTAL', 2, 'all', 2, 19, 3000, -10)"""
            )
        )
        return postgres_api_service

    @pytest.mark.integration
    def test_replacement_level_excludes_players_below_twenty_games(
        self, scenario, postgres_api_service
    ):
        postgres_api_service = scenario
        assert postgres_api_service.hockey_value(1001, 2025)[
            "hockeyValue"
        ] == pytest.approx(41.0)
        assert postgres_api_service.hockey_value(1005, 2025)[
            "hockeyValue"
        ] == pytest.approx(0.0)


class TestMeasuredZeroIsNotReportedAsMissing:
    @pytest.fixture
    def scenario(self, postgres_api_service):
        postgres_api_service.repository.session.execute(
            text(
                """INSERT INTO players
                     (id, first_name, last_name, primary_position, active, roster_status)
                   VALUES (1008, 'Zero', 'Scorer', 'C', TRUE, 'ACTIVE');
                   INSERT INTO player_team_stints
                     (player_id, season_start_year, team_id, joined_on)
                   VALUES (1008, 2025, 101, '2025-07-01');
                   INSERT INTO skater_season_stats
                     (player_id, season_start_year, team_id, stat_scope, game_type,
                      source_id, games_played, goals, assists, points, shots)
                   VALUES (1008, 2025, NULL, 'TOTAL', 2, 1, 20, 0, 0, 0, 0)"""
            )
        )
        return postgres_api_service

    @pytest.mark.integration
    def test_measured_zero_is_not_reported_as_missing(
        self, scenario, postgres_api_service
    ):
        postgres_api_service = scenario
        traditional = postgres_api_service.player_stats(1008, 2025)["traditional"]

        assert traditional["gamesPlayed"] == 20
        assert traditional["goals"] == 0
        assert traditional["points"] == 0
        assert traditional["shootingPercentage"] is None


@pytest.mark.integration
def test_minor_league_contract_uses_the_cba_buried_relief(postgres_api_service):
    cap = postgres_api_service.team_cap(101, 2025)

    assert cap["minorsCapCents"] == 0
    assert cap["totalCommitmentsCents"] == 0
    assert cap["capSpaceCents"] == cap["salaryCapCents"]


@pytest.mark.integration
@pytest.mark.parametrize(
    ("position", "team"),
    [
        pytest.param(None, None, id="all-eligible-players"),
        pytest.param("C", None, id="position-only"),
        pytest.param(None, "bbb", id="team-only"),
    ],
)
def test_leader_filters_and_null_values(postgres_api_service, position, team):
    leaders = postgres_api_service.leaders(2025, position, team, 10)
    assert all(row["hockeyValue"] is not None for row in leaders)
    if position is not None:
        assert all(row["primaryPosition"] == position for row in leaders)
    if team is not None:
        assert all(row["team"]["abbreviation"].casefold() == team for row in leaders)


@pytest.mark.integration
class TestQueryBoundaries:
    @pytest.fixture
    def page_queries(self, order):
        return tuple(
            PlayerQuery(season=2025, sort="points", order=order, page=page, page_size=2)
            for page in range(1, 4)
        )

    @pytest.fixture
    def injection_query(self):
        return PlayerQuery(
            season=2025, search="' OR TRUE --", sort="name", order="asc", page_size=10
        )

    @pytest.fixture
    def tied_service(self, postgres_api_service):
        postgres_api_service.repository.session.execute(
            text(
                "UPDATE skater_season_stats SET points=30 WHERE player_id IN (1003, 1005)"
            )
        )
        return postgres_api_service

    @pytest.fixture
    def missing_prediction_payload(self, postgres_api_service):
        postgres_api_service.repository.session.execute(
            text("""INSERT INTO predictions
                (model_version_id, player_id, target_season, position_group,
                 predicted_aav_cents, input_features)
                VALUES (3001, 1002, 2026, 'forward', 999999999, '{}')""")
        )
        return postgres_api_service

    @pytest.mark.parametrize(
        ("order", "expected"),
        [
            pytest.param(
                "desc", (1001, 1004, 1003, 1005, 1002, 1006), id="descending-nulls-last"
            ),
            pytest.param(
                "asc", (1002, 1003, 1005, 1004, 1001, 1006), id="ascending-nulls-last"
            ),
        ],
    )
    def test_ties_and_null_ordering_across_page_boundaries(
        self, tied_service, page_queries, expected
    ):
        pages = [tied_service.players(query) for query in page_queries]
        assert tuple(row["id"] for page in pages for row in page["data"]) == expected
        assert all(page["pagination"]["totalItems"] == 6 for page in pages)

    def test_search_text_is_bound_as_data(self, postgres_api_service, injection_query):
        result = postgres_api_service.players(injection_query)
        assert result["data"] == []
        assert result["pagination"]["totalItems"] == 0

    def test_aav_prediction_without_value_payload_is_not_a_value_projection(
        self, missing_prediction_payload
    ):
        result = missing_prediction_payload.hockey_value(1002, 2025)
        assert result["projectedNextSeasonHockeyValue"] is None

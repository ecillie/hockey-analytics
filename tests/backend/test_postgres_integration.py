from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.api.errors import ApiProblem
from app.api.repository import SqlApiRepository
from app.api.service import TradeValueService


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
def engine(disposable_database_url):
    database_engine = create_engine(disposable_database_url, pool_pre_ping=True)
    with database_engine.begin() as connection:
        assert (
            connection.execute(
                text("SELECT to_regclass('public.players')")
            ).scalar_one()
            == "players"
        )
        connection.exec_driver_sql(SEED_SQL)
    yield database_engine
    database_engine.dispose()


@pytest.fixture()
def service(engine):
    with Session(engine) as session:
        yield TradeValueService(repository=SqlApiRepository(session=session))


@pytest.mark.integration
def test_listing_prefers_total_rows_and_current_team(service):
    result = service.players(2025, None, None, None, None, "points", "desc", 1, 3)
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

    aggregated = service.players(
        2025, None, None, None, "Low Forward", "name", "asc", 1, 10
    )["data"][0]
    assert (aggregated["gamesPlayed"], aggregated["goals"], aggregated["points"]) == (
        20,
        2,
        5,
    )
    assert aggregated["team"]["abbreviation"] == "BBB"

    filtered = service.players(2025, "bbb", "C", "ACTIVE", "High", "name", "asc", 1, 10)
    assert [player["id"] for player in filtered["data"]] == [1004]


@pytest.mark.integration
def test_validation_missing_entities_and_nullable_identity(service):
    assert [team["id"] for team in service.teams()] == [101, 102]

    with pytest.raises(ApiProblem) as invalid:
        service.require_season(2099)
    assert (invalid.value.status, invalid.value.code) == (400, "INVALID_SEASON")

    with pytest.raises(ApiProblem) as player_missing:
        service.player_identity(9999)
    assert player_missing.value.code == "PLAYER_NOT_FOUND"

    with pytest.raises(ApiProblem) as team_missing:
        service.team_summary(9999)
    assert team_missing.value.code == "TEAM_NOT_FOUND"

    identity = service.player_identity(1007)
    assert identity["team"] is None
    assert identity["birthDate"] is None
    assert service.contract(1007, 2025) is None
    assert service.hockey_value(1007, 2025) == {
        "playerId": 1007,
        "season": 2025,
        "hockeyValue": None,
        "projectedNextSeasonHockeyValue": None,
        "gameScorePer60AboveReplacement": None,
        "toiHours": None,
        "modelVersion": None,
    }


@pytest.mark.integration
def test_season_catalog_and_validation_share_the_july_first_boundary(engine):
    with Session(engine) as session:
        before_cutoff = TradeValueService(
            repository=SqlApiRepository(session=session), as_of=date(2026, 6, 30)
        )
        before_info = before_cutoff.seasons()
        assert before_info["currentSeason"] == 2025
        assert max(s["startYear"] for s in before_info["availableSeasons"]) == 2025
        with pytest.raises(ApiProblem) as future:
            before_cutoff.require_season(2026)
        assert future.value.code == "INVALID_SEASON"

        on_cutoff = TradeValueService(
            repository=SqlApiRepository(session=session), as_of=date(2026, 7, 1)
        )
        on_cutoff_info = on_cutoff.seasons()
        assert on_cutoff_info["currentSeason"] == 2026
        assert max(s["startYear"] for s in on_cutoff_info["availableSeasons"]) == 2026
        on_cutoff.require_season(2026)


@pytest.mark.integration
def test_skater_goalie_history_and_value(service):
    skater = service.player_stats(1001, 2025)
    assert skater["traditional"]["gamesPlayed"] == 82
    assert skater["advanced"]["iceTimeSeconds"] == 98_400
    assert skater["goalie"] is None

    goalie = service.player_stats(1006, 2025)
    assert goalie["traditional"] is None
    assert goalie["goalie"]["gamesPlayed"] == 22
    assert goalie["goalie"]["goalsSavedAboveExpected"] == pytest.approx(5.0)

    value = service.hockey_value(1001, 2025)
    assert value["gameScorePer60AboveReplacement"] == pytest.approx(1.5)
    assert value["toiHours"] == pytest.approx(27.3333333)
    assert value["modelVersion"] == "integration-v1"
    assert service.value_history(1001) == [
        {"season": 2025, "hockeyValue": pytest.approx(41.0)}
    ]


@pytest.mark.integration
def test_team_roster_contract_and_raw_cap_subtotals(service):
    team = service.team(102)
    assert team["rosterCounts"] == {"ACTIVE": 3, "MINORS": 0, "LTIR": 1, "UNKNOWN": 0}

    roster = service.roster(102, 2025, "ACTIVE")
    assert [player["id"] for player in roster["players"]] == [1004, 1002, 1001]
    assert len(service.roster(102, 2025, None)["players"]) == 4

    contract = service.contract(1001, 2025)
    assert contract["signingTeam"]["abbreviation"] == "AAA"
    assert [season["season"] for season in contract["seasons"]] == [2025, 2026]
    assert contract["seasons"][0]["capHitCents"] == 800_000_000

    contracts = service.team_contracts(102, 2025)
    assert [row["player"]["id"] for row in contracts["contracts"]] == [1001, 1003]

    cap = service.team_cap(102, 2025)
    assert cap["activeRosterCapCents"] == 800_000_000
    assert cap["ltirCapCents"] == 200_000_000
    assert cap["minorsCapCents"] == 0
    assert cap["totalCommitmentsCents"] == 1_000_000_000
    assert cap["calculationStatus"] == "ESTIMATE"


@pytest.mark.integration
def test_search_leaders_overview_and_compare(service):
    found = service.search("Beta", ["player", "team"], 8)
    assert found["players"] == []
    assert [team["id"] for team in found["teams"]] == [102]
    players_only = service.search("Traded", ["player"], 8)
    assert [player["id"] for player in players_only["players"]] == [1001]
    assert players_only["teams"] == []

    leaders = service.leaders(2025, "C", "BBB", 5)
    assert [player["id"] for player in leaders] == [1004, 1001]

    overview = service.overview(2025)
    assert overview["league"]["players"] == 6
    assert overview["league"]["goals"] == 72
    assert overview["leaders"]["hockeyValue"][0]["id"] == 1004

    comparison = service.compare([1001, 1006], 2025)
    assert [row["player"]["id"] for row in comparison["players"]] == [1001, 1006]
    assert comparison["players"][0]["contract"] is not None
    assert comparison["players"][1]["stats"]["goalie"] is not None


@pytest.mark.integration
def test_known_player_without_season_data_returns_empty_stat_groups(service):
    stats = service.player_stats(1007, 2025)

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
    def scenario(self, service):
        service.repository.session.execute(
            text(
                """INSERT INTO model_versions
                     (id, model_type, version, artifact_uri, feature_schema,
                      training_start_season, training_end_season, active, created_at)
                   VALUES
                     (3002, 'skater_value', 'retired-v2', 'memory://retired', '{}',
                      2024, 2025, FALSE, CURRENT_TIMESTAMP + INTERVAL '1 day')"""
            )
        )
        service.repository.session.execute(
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
        return service

    @pytest.mark.integration
    def test_only_the_active_model_can_supply_the_current_projection(
        self, scenario, service
    ):
        service = scenario
        value = service.hockey_value(1001, 2025)

        assert value["modelVersion"] == "integration-v1"
        assert value["projectedNextSeasonHockeyValue"] == pytest.approx(42.5)


class TestReplacementLevelExcludesPlayersBelowTwentyGames:
    @pytest.fixture
    def scenario(self, service):
        service.repository.session.execute(
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
        return service

    @pytest.mark.integration
    def test_replacement_level_excludes_players_below_twenty_games(
        self, scenario, service
    ):
        service = scenario
        assert service.hockey_value(1001, 2025)["hockeyValue"] == pytest.approx(41.0)
        assert service.hockey_value(1005, 2025)["hockeyValue"] == pytest.approx(0.0)


class TestMeasuredZeroIsNotReportedAsMissing:
    @pytest.fixture
    def scenario(self, service):
        service.repository.session.execute(
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
        return service

    @pytest.mark.integration
    def test_measured_zero_is_not_reported_as_missing(self, scenario, service):
        service = scenario
        traditional = service.player_stats(1008, 2025)["traditional"]

        assert traditional["gamesPlayed"] == 20
        assert traditional["goals"] == 0
        assert traditional["points"] == 0
        assert traditional["shootingPercentage"] is None


@pytest.mark.integration
def test_minor_league_contract_uses_the_cba_buried_relief(service):
    cap = service.team_cap(101, 2025)

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
def test_leader_filters_and_null_values(service, position, team):
    leaders = service.leaders(2025, position, team, 10)
    assert all(row["hockeyValue"] is not None for row in leaders)
    if position is not None:
        assert all(row["primaryPosition"] == position for row in leaders)
    if team is not None:
        assert all(row["team"]["abbreviation"].casefold() == team for row in leaders)


@pytest.mark.integration
class TestQueryBoundaries:
    @pytest.fixture
    def tied_service(self, service):
        service.repository.session.execute(
            text(
                "UPDATE skater_season_stats SET points=30 WHERE player_id IN (1003, 1005)"
            )
        )
        return service

    @pytest.fixture
    def missing_prediction_payload(self, service):
        service.repository.session.execute(
            text("""INSERT INTO predictions
                (model_version_id, player_id, target_season, position_group,
                 predicted_aav_cents, input_features)
                VALUES (3001, 1002, 2026, 'forward', 999999999, '{}')""")
        )
        return service

    @pytest.mark.parametrize(
        ("order", "expected"),
        [
            pytest.param(
                "desc", [1001, 1004, 1003, 1005, 1002, 1006], id="descending-nulls-last"
            ),
            pytest.param(
                "asc", [1002, 1003, 1005, 1004, 1001, 1006], id="ascending-nulls-last"
            ),
        ],
    )
    def test_ties_and_null_ordering_across_page_boundaries(
        self, tied_service, order, expected
    ):
        pages = [
            tied_service.players(2025, None, None, None, None, "points", order, page, 2)
            for page in range(1, 4)
        ]
        assert [row["id"] for page in pages for row in page["data"]] == expected
        assert all(page["pagination"]["totalItems"] == 6 for page in pages)

    def test_search_text_is_bound_as_data(self, service):
        result = service.players(
            2025, None, None, None, "' OR TRUE --", "name", "asc", 1, 10
        )
        assert result["data"] == []
        assert result["pagination"]["totalItems"] == 0

    def test_aav_prediction_without_value_payload_is_not_a_value_projection(
        self, missing_prediction_payload
    ):
        result = missing_prediction_payload.hockey_value(1002, 2025)
        assert result["projectedNextSeasonHockeyValue"] is None

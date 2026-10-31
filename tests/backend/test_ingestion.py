from contextlib import contextmanager, nullcontext
from collections.abc import Generator
from psycopg2.extensions import connection as PgConnection
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TypedDict
from app.shared.tests.fakes import StageOutcome
from app.ScriptingFiles.FullDataScript.source_ingestion.tests.responses import (
    SavedJsonSession,
    MoneyPuckSession,
    CapWagesSession,
    InvalidContractSession,
    SessionLifecycle,
    ScheduleSession,
    NhlRosterSession,
)

import pytest
import psycopg2
from psycopg2.errors import lookup
from app.ScriptingFiles.FullDataScript import ingestion_tracking
from app.ScriptingFiles.FullDataScript import (
    capspace,
    ingestion,
    populate_roster_status,
    team_stints,
)
from app.ScriptingFiles.FullDataScript.contracts.domain import ActivePlayer
from app.ScriptingFiles.FullDataScript.contracts.errors import MoneyParseError
from app.ScriptingFiles.FullDataScript.contracts.schemas.active import (
    capwages_birth_date,
    parse_active_players,
)
from app.ScriptingFiles.FullDataScript.roster_status.domain import (
    ExternalRosterPlayer,
    FetchResult,
)
from app.ScriptingFiles.FullDataScript.roster_status.tests.fakes import FixedRosterFeed
from app.ScriptingFiles.FullDataScript.source_ingestion import util as source_utils
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.repository import (
    PostgresMoneyPuckRepository,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.services import (
    MoneyPuckService,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.tests.fakes import (
    MemorySourceClient,
)
from sqlalchemy import create_engine, text

FIXTURES = Path(__file__).parent.joinpath("fixtures", "ingestion")


@dataclass(slots=True, kw_only=True, frozen=True)
class RosterFeedScenario:
    nhl: FixedRosterFeed
    ahl: FixedRosterFeed


class MoneyPuckFixtureOptions(TypedDict):
    expected_seasons: tuple[int, ...]
    minimum_rows_per_kind: int
    maximum_duplicate_ratio: float


def test_season_and_ordered_team_helpers():
    assert ingestion._season_start_year(date(2026, 6, 30)) == 2025
    assert ingestion._season_start_year(date(2026, 7, 1)) == 2026
    assert source_utils.ordered_team_abbreviations("COL,CAR,DAL") == (
        "COL",
        "CAR",
        "DAL",
    )
    assert source_utils.ordered_team_abbreviations(" TOT, bad value,NYR ") == ("NYR",)


def nhl_stat_rows(kind, season, game_type, *, goals=5):
    if kind == "skater":
        row = {
            "playerId": 1001,
            "skaterFullName": "Fixture Skater",
            "teamAbbrevs": "AAA,BBB",
            "positionCode": "C",
            "gamesPlayed": 10,
            "goals": goals,
            "assists": 7,
            "points": goals + 7,
            "shots": 40,
        }
    else:
        row = {
            "playerId": 2001,
            "goalieFullName": "Fixture Goalie",
            "teamAbbrevs": "BBB",
            "gamesPlayed": 8,
            "wins": 5,
            "losses": 2,
            "otLosses": 1,
            "shotsAgainst": 220,
            "saves": 207,
            "goalsAgainst": 13,
        }
    return [row, dict(row)]


def test_csv_parser_rejects_duplicate_columns_and_extra_values():
    with pytest.raises(
        ingestion.IngestionValidationError, match="duplicate CSV columns"
    ):
        source_utils.parse_csv("playerId,playerId\n1,2\n", source="fixture")

    with pytest.raises(ingestion.IngestionValidationError, match="too many values"):
        source_utils.parse_csv("playerId,season\n1,2025,extra\n", source="fixture")


class TestRequiredFieldsAndSeasonTypeValidation:
    @pytest.fixture
    def scenario(self, season):
        row = {"playerId": "1", "season": season, "name": "A Player"}
        return row

    @pytest.mark.parametrize(
        "season",
        [
            pytest.param(None, id="missing"),
            pytest.param("", id="empty"),
            pytest.param("  ", id="whitespace"),
            pytest.param("twenty", id="non-numeric"),
            pytest.param("2025.5", id="fractional"),
            pytest.param("0", id="zero"),
            pytest.param("Infinity", id="nonfinite"),
        ],
    )
    def test_required_fields_and_season_type_validation(self, scenario, season):
        row = scenario
        with pytest.raises(ingestion.IngestionValidationError):
            ingestion.validate_and_deduplicate_rows(
                [row],
                source="fixture",
                required_fields=("playerId", "season", "name"),
                grain_fields=("playerId", "season"),
            )


def test_validation_rejects_empty_inputs_and_schema_drift():
    with pytest.raises(ingestion.IngestionValidationError, match="no rows"):
        ingestion.validate_and_deduplicate_rows(
            [],
            source="fixture",
            required_fields=("playerId",),
            grain_fields=("playerId",),
        )

    with pytest.raises(
        ingestion.IngestionValidationError, match="games_played must be"
    ):
        ingestion.validate_and_deduplicate_rows(
            [
                {
                    "playerId": "1",
                    "season": "2025",
                    "name": "A Player",
                    "games_played": "10.5",
                }
            ],
            source="fixture",
            required_fields=("playerId", "season", "name", "games_played"),
            grain_fields=("playerId", "season"),
            integer_fields=("playerId", "season", "games_played"),
        )
    with pytest.raises(
        ingestion.IngestionValidationError, match="missing required columns: name"
    ):
        ingestion.validate_and_deduplicate_rows(
            [{"playerId": "1", "season": "2025"}],
            source="fixture",
            required_fields=("playerId", "season", "name"),
            grain_fields=("playerId", "season"),
        )


class TestValidationDeduplicatesAtPlayerSeasonStatGrainAndChecksCoverage:
    @pytest.fixture
    def scenario(self):
        rows = [
            {
                "playerId": "1",
                "season": "2024",
                "team": "AAA",
                "situation": "all",
                "value": "old",
            },
            {
                "playerId": "1",
                "season": "2024",
                "team": "aaa",
                "situation": "ALL",
                "value": "new",
            },
            {
                "playerId": "1",
                "season": "2025",
                "team": "AAA",
                "situation": "all",
                "value": "next",
            },
        ]
        return rows

    def test_validation_deduplicates_at_player_season_stat_grain_and_checks_coverage(
        self, scenario
    ):
        rows = scenario
        valid, report = ingestion.validate_and_deduplicate_rows(
            rows,
            source="fixture",
            required_fields=("playerId", "season", "situation"),
            grain_fields=("playerId", "season", "team", "situation"),
            expected_seasons=(2024, 2025),
        )
        assert [row["value"] for row in valid] == ["new", "next"]
        assert report.records_read == 3
        assert report.records_valid == 2
        assert report.duplicate_records == 1
        assert report.seasons == (2024, 2025)

        with pytest.raises(ingestion.IngestionValidationError, match="duplicate ratio"):
            ingestion.enforce_quality_thresholds(
                report, minimum_rows=2, maximum_duplicate_ratio=0.10
            )
        with pytest.raises(ingestion.IngestionValidationError, match="minimum is 3"):
            ingestion.enforce_quality_thresholds(
                report, minimum_rows=3, maximum_duplicate_ratio=1.0
            )

        with pytest.raises(
            ingestion.IngestionValidationError, match="missing seasons: 2023"
        ):
            ingestion.validate_and_deduplicate_rows(
                rows,
                source="fixture",
                required_fields=("playerId", "season", "situation"),
                grain_fields=("playerId", "season", "team", "situation"),
                expected_seasons=(2023, 2024, 2025),
            )


def test_value_coercion_contract_money_and_capwages_player_parsing():
    assert source_utils.parse_number("12.75") == 12.75
    assert source_utils.parse_number("12", integer=True) == 12
    assert source_utils.parse_number("NaN") is None
    assert source_utils.parse_number("bad") is None
    assert ingestion._money_cents("$1,234.56") == 123456
    with pytest.raises(MoneyParseError):
        ingestion._money_cents("bad")
    assert capwages_birth_date("97-1-13") == "1997-01-13"
    assert capwages_birth_date("97-99-13") is None

    capwages_row = ["Fixture Player", None, "AAA", "L"] + [None] * 27
    capwages_row[7] = "CAN"
    capwages_row[30] = "97-1-13"
    assert parse_active_players([capwages_row], minimum_rows=1) == (
        ActivePlayer(
            name="Fixture Player",
            slug="fixture-player",
            team="AAA",
            position="L",
            nationality="CAN",
            birth_date="1997-01-13",
        ),
    )
    with pytest.raises(ingestion.IngestionValidationError, match="minimum is 2"):
        parse_active_players([capwages_row], minimum_rows=2)


def test_cross_field_stat_invariants_reject_inconsistent_rows():
    with pytest.raises(ingestion.IngestionValidationError, match="points must equal"):
        ingestion.validate_stat_invariants(
            "skater",
            {"playerId": 1, "goals": 2, "assists": 3, "points": 99},
            source="fixture",
        )
    with pytest.raises(ingestion.IngestionValidationError, match="shotsAgainst"):
        ingestion.validate_stat_invariants(
            "goalie",
            {"playerId": 2, "shotsAgainst": 20, "saves": 18, "goalsAgainst": 3},
            source="fixture",
        )


def test_nhl_api_parser_rejects_schema_drift():
    session = SavedJsonSession(payload={"data": {"not": "a list"}})
    with pytest.raises(ingestion.IngestionValidationError, match="data must be a list"):
        ingestion._nhl_stats_pages(session, "skater", 2025, 2)

    session = SavedJsonSession(payload={"data": [{"goals": 1}]})
    with pytest.raises(ingestion.IngestionValidationError, match="missing playerId"):
        ingestion._nhl_stats_pages(session, "skater", 2025, 2)


class TestRetainedSnapshots:
    expected = {"players": 600, "contracts": 500, "contract_seasons": 900, "cached": 1}
    historical = {
        "total_player_seasons": 100,
        "covered_player_seasons": 100,
        "missing_player_seasons": 0,
        "cached": 1,
    }

    @pytest.fixture(
        params=[
            pytest.param("capwages", id="retain-active-contracts"),
            pytest.param("historical", id="retain-historical-contracts"),
            pytest.param("moneypuck", id="reject-stats-failure"),
        ]
    )
    def stages(self, request, monkeypatch):
        events = []
        stages = (
            (
                ingestion,
                "init_db",
                StageOutcome(result=None, name="init", events=events),
            ),
            (
                ingestion,
                "http_session",
                StageOutcome(result=SessionLifecycle(), name="session", events=events),
            ),
            (
                ingestion,
                "ingest_moneypuck",
                StageOutcome(
                    result={},
                    failure=RuntimeError("bad stats")
                    if request.param == "moneypuck"
                    else None,
                    name="moneypuck",
                    events=events,
                ),
            ),
            (
                ingestion,
                "ingest_nhl_rosters",
                StageOutcome(result={}, name="rosters", events=events),
            ),
            (
                ingestion,
                "ingest_nhl_stats",
                StageOutcome(result={}, name="stats", events=events),
            ),
            (
                ingestion,
                "ingest_capwages",
                StageOutcome(
                    result={},
                    failure=RuntimeError("partial feed")
                    if request.param == "capwages"
                    else None,
                    name="capwages",
                    events=events,
                ),
            ),
            (
                ingestion,
                "existing_capwages_summary",
                StageOutcome(result=self.expected, name="active-cache", events=events),
            ),
            (
                capspace,
                "ingest_historical_contracts",
                StageOutcome(
                    result=self.historical,
                    failure=RuntimeError("CapSpace down")
                    if request.param == "historical"
                    else None,
                    name="historical",
                    events=events,
                ),
            ),
            (
                capspace,
                "existing_historical_contract_summary",
                StageOutcome(
                    result=self.historical, name="historical-cache", events=events
                ),
            ),
            (
                ingestion,
                "ingest_schedule",
                StageOutcome(result={"games": 10}, name="schedule", events=events),
            ),
        )
        for module, name, stage in stages:
            monkeypatch.setattr(module, name, stage)
        return request.param, events

    def test_only_contract_failures_can_retain_the_last_good_snapshot(self, stages):
        failed_stage, events = stages
        if failed_stage == "moneypuck":
            with pytest.raises(RuntimeError, match="bad stats"):
                ingestion.run_all()
            assert events == ["init", "session", "moneypuck"]
            return
        result = ingestion.run_all()
        assert result["historical_contracts"] == self.historical
        assert result["schedule"] == {"games": 10}
        if failed_stage == "capwages":
            assert result["capwages"] == self.expected
            assert "active-cache" in events
        if failed_stage == "historical":
            assert "historical-cache" in events


class TestRosterCommandStatuses:
    summary = {
        "statuses_updated": 1,
        "active_count": 1,
        "minors_count": 0,
        "ltir_count": 0,
        "unknown_count": 0,
        "preserved_count": 0,
    }

    @pytest.fixture(
        params=[
            pytest.param((None, 0), id="complete"),
            pytest.param(
                (
                    populate_roster_status.IncompleteRosterFeedError(
                        errors=("partial",)
                    ),
                    2,
                ),
                id="incomplete",
            ),
            pytest.param((RuntimeError("database unavailable"), 1), id="failed"),
        ]
    )
    def status(self, request, monkeypatch):
        failure, status = request.param
        monkeypatch.setattr(
            populate_roster_status, "init_db", StageOutcome(result=None)
        )
        monkeypatch.setattr(
            populate_roster_status,
            "sync_roster_status",
            StageOutcome(result=self.summary, failure=failure),
        )
        return status

    def test_roster_command_exit_codes(self, status):
        assert populate_roster_status.main([]) == status


@pytest.fixture()
def migrated_database(monkeypatch, tmp_path, disposable_database_url):
    engine = create_engine(disposable_database_url)
    with engine.begin() as connection:
        if (
            connection.execute(
                text("SELECT to_regclass('public.players')")
            ).scalar_one()
            is None
        ):
            raise pytest.skip.Exception("the test database has not been migrated")
        connection.execute(
            text("TRUNCATE teams, players, ingestion_runs RESTART IDENTITY CASCADE")
        )

    @contextmanager
    def test_transaction() -> Generator[PgConnection]:

        connection = psycopg2.connect(disposable_database_url)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    monkeypatch.setattr(ingestion, "database_transaction", test_transaction)
    for folder, name, fixture_name in (
        ("skater advanced", "skaters_2008_to_2024.csv", "moneypuck_skaters.csv"),
        ("goalie_advanced", "goalies_2008_to_2024.csv", "moneypuck_goalies.csv"),
    ):
        destination = tmp_path.joinpath(folder, name)
        destination.parent.mkdir()
        destination.write_text(FIXTURES.joinpath(fixture_name).read_text())
    monkeypatch.setenv("TRADEVALUE_DATA_DIR", str(tmp_path))
    yield engine
    engine.dispose()


class TestMoneypuckIngestionIsIdempotentDeduplicatedAndUpdatesTypedValues:
    @pytest.fixture
    def scenario(self):
        options: MoneyPuckFixtureOptions = {
            "expected_seasons": (2024, 2025),
            "minimum_rows_per_kind": 2,
            "maximum_duplicate_ratio": 0.5,
        }
        return options

    @pytest.mark.integration
    def test_moneypuck_ingestion_is_idempotent_deduplicated_and_updates_typed_values(
        self, scenario, migrated_database
    ):
        options = scenario
        first = ingestion.ingest_moneypuck(MoneyPuckSession(skater_games=12), **options)
        second = ingestion.ingest_moneypuck(
            MoneyPuckSession(skater_games=15), **options
        )
        expected_common = {
            "players": 2,
            "skater": 2,
            "goalie": 2,
            "records_read": 5,
            "records_skipped": 1,
            "reconciliation_policy": "retain_missing",
        }
        assert {key: first[key] for key in expected_common} == expected_common
        assert {key: second[key] for key in expected_common} == expected_common
        assert (first["records_created"], first["records_updated"]) == (4, 0)
        assert (second["records_created"], second["records_updated"]) == (0, 4)

        with migrated_database.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM players")).scalar_one()
                == 2
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM skater_advanced_season_stats")
                ).scalar_one()
                == 2
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM goalie_advanced_season_stats")
                ).scalar_one()
                == 2
            )
            games = connection.execute(
                text(
                    "SELECT games_played FROM skater_advanced_season_stats WHERE season_start_year=2025"
                )
            ).scalar_one()
            assert games == 15
            cap = connection.execute(
                text("SELECT salary_cap_cents FROM seasons WHERE start_year=2025")
            ).scalar_one()
            assert cap == 9_550_000_000


@pytest.mark.integration
def test_set_based_team_stint_backfill_is_idempotent(
    migrated_database, disposable_database_url
):

    ingestion.ingest_moneypuck(
        MoneyPuckSession(),
        expected_seasons=(2024, 2025),
        minimum_rows_per_kind=2,
        maximum_duplicate_ratio=0.5,
    )

    connection = psycopg2.connect(disposable_database_url)
    try:
        assert team_stints.plan_team_stint_backfill(connection) == {
            "canonical_assignments": 4,
            "missing_assignments": 4,
        }
        assert team_stints.apply_team_stint_backfill(connection) == {
            "canonical_assignments": 4,
            "missing_assignments": 4,
            "inserted_assignments": 4,
        }
        connection.commit()
        assert team_stints.apply_team_stint_backfill(connection) == {
            "canonical_assignments": 4,
            "missing_assignments": 0,
            "inserted_assignments": 0,
        }
        connection.commit()
    finally:
        connection.close()

    with migrated_database.connect() as connection:
        rows = connection.execute(
            text(
                """SELECT pts.season_start_year, t.abbreviation
               FROM player_team_stints pts
               JOIN teams t ON t.id = pts.team_id
               ORDER BY pts.season_start_year, t.abbreviation"""
            )
        ).all()
        assert rows == [(2024, "AAA"), (2024, "BBB"), (2025, "AAA"), (2025, "BBB")]


@pytest.mark.integration
def test_failed_ingestion_rolls_back_players_teams_and_stats(migrated_database):

    with pytest.raises(lookup("23503")):
        ingestion.ingest_moneypuck(
            MoneyPuckSession(season=2199),
            expected_seasons=(2024, 2199),
            minimum_rows_per_kind=2,
            maximum_duplicate_ratio=0.5,
        )
    with migrated_database.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM players")).scalar_one() == 0
        )
        assert connection.execute(text("SELECT count(*) FROM teams")).scalar_one() == 0
        assert (
            connection.execute(
                text("SELECT count(*) FROM skater_advanced_season_stats")
            ).scalar_one()
            == 0
        )


@pytest.mark.integration
def test_contract_and_salary_cap_ingestion_is_idempotent_and_upserts(migrated_database):

    first = ingestion.ingest_capwages(CapWagesSession(), minimum_players=1)
    second = ingestion.ingest_capwages(
        CapWagesSession(cap_hit="$1,250,000"), minimum_players=1
    )
    expected_common = {
        "players": 1,
        "contracts": 1,
        "contract_seasons": 1,
        "profile_failures": 0,
        "records_read": 3,
        "records_skipped": 0,
        "reconciliation_policy": "retain_missing",
    }
    assert {key: first[key] for key in expected_common} == expected_common
    assert {key: second[key] for key in expected_common} == expected_common
    assert (first["records_created"], first["records_updated"]) == (2, 0)
    assert (second["records_created"], second["records_updated"]) == (0, 2)

    with migrated_database.connect() as connection:
        result = connection.execute(
            text("""
            SELECT count(*) OVER (), cs.cap_hit_cents, cs.cap_percentage,
                   c.total_value_cents, c.average_value_cents
            FROM contracts c JOIN contract_seasons cs ON cs.contract_id = c.id
        """)
        ).one()
        assert result[0] == 1
        assert result[1] == 125_000_000
        assert float(result[2]) == pytest.approx(125_000_000 / 9_550_000_000)
        assert result[3] == 200_000_000
        assert result[4] == 125_000_000


@pytest.mark.integration
def test_partial_contract_profile_refresh_is_rejected_before_database_writes(
    migrated_database,
):

    with pytest.raises(
        ingestion.IngestionValidationError, match="refusing partial refresh"
    ):
        ingestion.ingest_capwages(
            CapWagesSession(fail_profile=True),
            minimum_players=1,
            minimum_profile_success_ratio=1.0,
        )
    with migrated_database.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM contracts")).scalar_one() == 0
        )
        run = connection.execute(
            text("""
            SELECT status, error_message FROM ingestion_runs
            WHERE job_name='ingest_capwages' ORDER BY id DESC LIMIT 1
        """)
        ).one()
        assert run[0] == "failed"
        assert "refusing partial refresh" in run[1]


@pytest.mark.integration
def test_contract_rejects_noncontiguous_years_and_impossible_cap_hit(migrated_database):

    with pytest.raises(ingestion.IngestionValidationError, match="non-contiguous"):
        ingestion.ingest_capwages(InvalidContractSession(mode="gap"), minimum_players=1)
    with pytest.raises(
        ingestion.IngestionValidationError, match="exceeds the season salary cap"
    ):
        ingestion.ingest_capwages(InvalidContractSession(mode="cap"), minimum_players=1)
    with migrated_database.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM contracts")).scalar_one() == 0
        )


@pytest.mark.integration
def test_nhl_stats_are_deduplicated_idempotent_and_retain_missing_rows(
    migrated_database, monkeypatch
):

    first = ingestion.ingest_nhl_stats(
        first_season=2025, last_season=2025, client_factory=FixtureStatsFactory(goals=5)
    )
    second = ingestion.ingest_nhl_stats(
        first_season=2025, last_season=2025, client_factory=FixtureStatsFactory(goals=8)
    )
    expected_common = {
        "skater": 2,
        "goalie": 2,
        "records_read": 8,
        "records_skipped": 4,
        "reconciliation_policy": "retain_missing",
    }
    assert {key: first[key] for key in expected_common} == expected_common
    assert {key: second[key] for key in expected_common} == expected_common
    assert (first["records_created"], first["records_updated"]) == (4, 0)
    assert (second["records_created"], second["records_updated"]) == (0, 4)
    with migrated_database.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM skater_season_stats")
            ).scalar_one()
            == 2
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM goalie_season_stats")
            ).scalar_one()
            == 2
        )
        assert (
            connection.execute(
                text("""
            SELECT goals FROM skater_season_stats WHERE game_type=2
        """)
            ).scalar_one()
            == 8
        )
        assert (
            connection.execute(
                text("""
            SELECT count(*) FROM skater_season_stats WHERE stat_scope='TOTAL' AND team_id IS NULL
        """)
            ).scalar_one()
            == 2
        )
        stint_teams = (
            connection.execute(
                text("""
            SELECT DISTINCT t.abbreviation
            FROM player_team_stints pts JOIN teams t ON t.id=pts.team_id
            WHERE pts.season_start_year=2025
        """)
            )
            .scalars()
            .all()
        )
        assert stint_teams == ["BBB"]


@pytest.mark.integration
def test_nhl_roster_loader_enforces_completeness_and_upserts(migrated_database):

    with pytest.raises(ingestion.IngestionValidationError, match="minimum is 2"):
        ingestion.ingest_nhl_rosters(
            NhlRosterSession(), minimum_teams=2, minimum_active_players=1
        )
    first = ingestion.ingest_nhl_rosters(
        NhlRosterSession(), minimum_teams=1, minimum_active_players=1
    )
    second = ingestion.ingest_nhl_rosters(
        NhlRosterSession(), minimum_teams=1, minimum_active_players=1
    )
    assert first == second == {"teams": 1, "active_players": 1}
    with migrated_database.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM players")).scalar_one() == 1
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM player_team_stints")
            ).scalar_one()
            == 1
        )
        statuses = (
            connection.execute(
                text("""
            SELECT status FROM ingestion_runs WHERE job_name='ingest_nhl_rosters' ORDER BY id
        """)
            )
            .scalars()
            .all()
        )
        assert statuses == ["failed", "succeeded", "succeeded"]


@pytest.mark.integration
def test_schedule_upsert_retains_games_missing_from_a_later_snapshot(migrated_database):

    first = ingestion.ingest_schedule(ScheduleSession(), season=2025, minimum_games=1)
    second = ingestion.ingest_schedule(
        ScheduleSession(game_ids=(2025020001,)), season=2025, minimum_games=1
    )
    assert first["games"] == 2
    assert second == {
        "games": 1,
        "records_read": 1,
        "records_created": 0,
        "records_updated": 1,
        "records_skipped": 0,
        "reconciliation_policy": "retain_missing",
    }
    with migrated_database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM games")).scalar_one() == 2


class TestCrossSourceIdentityUsesExternalIdAndAvoidsAmbiguousNames:
    @pytest.fixture
    def scenario(self):
        options: MoneyPuckFixtureOptions = {
            "expected_seasons": (2024, 2025),
            "minimum_rows_per_kind": 2,
            "maximum_duplicate_ratio": 0.5,
        }
        return options

    @pytest.mark.integration
    def test_cross_source_identity_uses_external_id_and_avoids_ambiguous_names(
        self, scenario, migrated_database, monkeypatch
    ):
        options = scenario
        ingestion.ingest_moneypuck(MoneyPuckSession(), **options)
        ingestion.ingest_nhl_stats(
            first_season=2025,
            last_season=2025,
            client_factory=FixtureStatsFactory(goals=5),
        )
        with migrated_database.begin() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM players")).scalar_one()
                == 2
            )
            linked = connection.execute(
                text("""
                SELECT count(DISTINCT player_id) FROM player_external_ids
                WHERE external_id='1001' AND source_id IN (
                    SELECT id FROM data_sources WHERE code IN ('nhl','moneypuck')
                )
            """)
            ).scalar_one()
            assert linked == 1
            connection.execute(
                text("""
                INSERT INTO players (first_name,last_name) VALUES ('Fixture','Skater')
            """)
            )

        ingestion.ingest_capwages(
            CapWagesSession(player_name="Fixture Skater"), minimum_players=1
        )
        with migrated_database.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM players")).scalar_one()
                == 4
            )


@pytest.mark.integration
def test_ingestion_foreign_keys_and_grain_indexes_match_loader_contract(
    migrated_database,
):

    with migrated_database.connect() as connection:
        constraints = connection.execute(
            text("""
            SELECT conname, confdeltype
            FROM pg_constraint
            WHERE conname IN (
                'player_external_ids_player_id_fkey',
                'contracts_player_id_fkey',
                'contract_seasons_contract_id_fkey'
            )
        """)
        ).all()
        assert dict(constraints) == {
            "player_external_ids_player_id_fkey": "c",
            "contracts_player_id_fkey": "r",
            "contract_seasons_contract_id_fkey": "c",
        }
        indexes = (
            connection.execute(
                text("""
            SELECT indexname FROM pg_indexes
            WHERE indexname IN (
                'skater_season_stats_grain_idx',
                'goalie_season_stats_grain_idx',
                'skater_advanced_stats_grain_idx',
                'goalie_advanced_stats_grain_idx',
                'contracts_source_external_id_idx'
            )
        """)
            )
            .scalars()
            .all()
        )
        assert len(indexes) == 5


@pytest.mark.integration
def test_ingestion_run_tracking_and_concurrent_run_lock(
    migrated_database, disposable_database_url
):

    @ingestion_tracking.tracked_ingestion("nhl", "overlap_fixture")
    def fixture_stage():
        return {"rows": 1}

    lock_connection = psycopg2.connect(disposable_database_url)
    try:
        with lock_connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_lock(%s)",
                (ingestion_tracking.advisory_lock_key("overlap_fixture"),),
            )
        lock_connection.commit()
        with pytest.raises(
            ingestion_tracking.ConcurrentIngestionError, match="already running"
        ):
            fixture_stage()
    finally:
        with lock_connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_unlock(%s)",
                (ingestion_tracking.advisory_lock_key("overlap_fixture"),),
            )
        lock_connection.commit()
        lock_connection.close()

    assert fixture_stage() == {"rows": 1}
    with migrated_database.connect() as connection:
        runs = connection.execute(
            text("""
            SELECT status,records_read,records_updated,error_message
            FROM ingestion_runs WHERE job_name='overlap_fixture' ORDER BY id
        """)
        ).all()
        assert [row[0] for row in runs] == ["cancelled", "succeeded"]
        assert runs[1][1:3] == (1, 1)
        assert "already holds" in runs[0][3]


@pytest.mark.integration
class TestRosterTransactions:
    @pytest.fixture
    def roster_database(self, migrated_database):
        with migrated_database.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO players (id,first_name,last_name,birth_date,roster_status) VALUES
                    (11,'Active','Fixture','1990-01-01','MINORS'),
                    (12,'Minor','Fixture','1991-02-02','ACTIVE'),
                    (13,'Injured','Fixture','1992-03-03','ACTIVE');
                INSERT INTO player_external_ids (player_id,source_id,external_id)
                    SELECT player_id, id, player_id::text FROM data_sources
                    CROSS JOIN (VALUES (11),(12),(13)) AS p(player_id) WHERE code='nhl';
                INSERT INTO ltir_overrides (player_id,start_date) VALUES (13,'2025-01-01');
            """)
            )
        return migrated_database

    @pytest.fixture
    def feeds(self):
        nhl = FixedRosterFeed(
            result=FetchResult(
                items=(
                    ExternalRosterPlayer(external_id="11", full_name="Renamed Active"),
                )
            )
        )
        ahl = FixedRosterFeed(
            result=FetchResult(
                items=(
                    ExternalRosterPlayer(
                        external_id="ahl-12",
                        full_name="Minor Fixture",
                        birth_date=date(1991, 2, 2),
                    ),
                )
            )
        )
        return RosterFeedScenario(nhl=nhl, ahl=ahl)

    def test_complete_feeds_commit_statuses_and_identity_mapping(
        self, roster_database, feeds
    ):
        nhl, ahl = feeds.nhl, feeds.ahl
        summary = populate_roster_status.sync_roster_status(
            nhl_service=nhl, ahl_service=ahl, as_of=date(2025, 10, 1)
        )
        assert (
            summary["active_count"],
            summary["minors_count"],
            summary["ltir_count"],
        ) == (1, 1, 1)
        with roster_database.connect() as connection:
            assert dict(
                connection.execute(
                    text("SELECT id,roster_status::text FROM players ORDER BY id")
                ).all()
            ) == {11: "ACTIVE", 12: "MINORS", 13: "LTIR"}
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM player_external_ids p JOIN data_sources s ON s.id=p.source_id WHERE s.code='ahl' AND p.player_id=12 AND p.external_id='ahl-12'"
                    )
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text(
                        "SELECT status FROM ingestion_runs WHERE job_name='populate_roster_status'"
                    )
                ).scalar_one()
                == "succeeded"
            )

    @pytest.fixture(
        params=[
            pytest.param("nhl", id="incomplete-nhl"),
            pytest.param("ahl", id="incomplete-ahl"),
        ]
    )
    def partial_feeds(self, request, feeds):
        nhl, ahl = feeds.nhl, feeds.ahl
        if request.param == "nhl":
            nhl = FixedRosterFeed(
                result=FetchResult(
                    items=nhl.result.items, errors=("one NHL team failed",)
                )
            )
        if request.param == "ahl":
            ahl = FixedRosterFeed(
                result=FetchResult(
                    items=ahl.result.items, errors=("one AHL team failed",)
                )
            )
        return RosterFeedScenario(nhl=nhl, ahl=ahl)

    def test_incomplete_feed_rolls_back_statuses_and_new_external_ids(
        self, roster_database, partial_feeds
    ):
        nhl, ahl = partial_feeds.nhl, partial_feeds.ahl
        with pytest.raises(populate_roster_status.IncompleteRosterFeedError):
            populate_roster_status.sync_roster_status(
                nhl_service=nhl, ahl_service=ahl, as_of=date(2025, 10, 1)
            )
        with roster_database.connect() as connection:
            assert dict(
                connection.execute(
                    text("SELECT id,roster_status::text FROM players ORDER BY id")
                ).all()
            ) == {11: "MINORS", 12: "ACTIVE", 13: "ACTIVE"}
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM player_external_ids p JOIN data_sources s ON s.id=p.source_id WHERE s.code='ahl'"
                    )
                ).scalar_one()
                == 0
            )
            assert (
                connection.execute(
                    text(
                        "SELECT status FROM ingestion_runs WHERE job_name='populate_roster_status'"
                    )
                ).scalar_one()
                == "failed"
            )


@dataclass(slots=True, kw_only=True, frozen=True)
class FixtureStatsClient:
    goals: int
    csv_text: str = ""

    def get_json(self, url, *, timeout=30, params=None):
        kind = "skater" if "/skater/" in url else "goalie"
        assert params is not None
        season = int(params["cayenneExp"].split("=", 1)[1][:4])
        game_type = int(params["cayenneExp"][-1])
        return {"data": nhl_stat_rows(kind, season, game_type, goals=self.goals)}

    def get_csv(self, url, *, timeout=60):
        return self.csv_text


@dataclass(slots=True, kw_only=True, frozen=True)
class FixtureStatsFactory:
    goals: int

    def __call__(self):
        return nullcontext(FixtureStatsClient(goals=self.goals))


@pytest.mark.integration
class TestRetainedMoneyPuckRows:
    @pytest.fixture
    def results(self, migrated_database, source_puck_options, source_puck_csv):
        repository = PostgresMoneyPuckRepository(
            transaction=ingestion.database_transaction
        )
        initial_csv = dict(source_puck_csv)
        initial_csv[source_puck_options.skater_url] += (
            "3,2025,Extra Player,AAA,C,all,20,1800,7.5\n"
        )
        first = MoneyPuckService(
            client=MemorySourceClient(csv_files=initial_csv),
            repository=repository,
            options=source_puck_options,
        ).ingest()
        second = MoneyPuckService(
            client=MemorySourceClient(csv_files=source_puck_csv),
            repository=repository,
            options=source_puck_options,
        ).ingest()
        return migrated_database, first, second

    def test_absent_stat_rows_and_external_identity_are_retained(self, results):
        database, first, second = results
        assert (
            first.counts.records_created,
            second.counts.records_created,
            second.counts.records_updated,
        ) == (5, 0, 4)
        with database.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM skater_advanced_season_stats")
                ).scalar_one()
                == 3
            )
            assert (
                connection.execute(text("SELECT count(*) FROM players")).scalar_one()
                == 3
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM player_external_ids WHERE external_id='3'"
                    )
                ).scalar_one()
                == 1
            )

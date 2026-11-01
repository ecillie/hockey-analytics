from datetime import date
from pathlib import Path
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
from app.config import AppEnvironment, DatabaseSettings
from app.database import open_database_cursor, open_database_transaction
from psycopg2.errors import lookup
from app.ScriptingFiles.FullDataScript import ingestion_tracking
from app.ScriptingFiles.FullDataScript.tracking.repository import count_summary_records
from app.ScriptingFiles.FullDataScript import (
    capspace,
    ingestion,
    populate_roster_status,
    team_stints,
)
from app.ScriptingFiles.FullDataScript.contracts.domain import ActivePlayer
from app.ScriptingFiles.FullDataScript.contracts.errors import MoneyParseError
from app.ScriptingFiles.FullDataScript.source_ingestion.errors import (
    PlayerKindViolation,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.active import (
    parse_capwages_birth_date,
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
from sqlalchemy import text
from app.ScriptingFiles.FullDataScript.source_ingestion.tests.responses import (
    FixtureStatsFactory,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.tests.scenarios import (
    RosterFeedScenario,
    MoneyPuckFixtureOptions,
    RetainedStageScenario,
    RetainedMoneyPuckScenario,
)

FIXTURES = Path(__file__).parent.joinpath("fixtures", "ingestion")


class TestDurableRunCounts:
    cases = (
        pytest.param(True, 7, id="true-is-not-a-count"),
        pytest.param(False, 7, id="false-is-not-a-count"),
        pytest.param(-1, 7, id="negative-is-not-a-count"),
        pytest.param(None, 7, id="null-is-not-a-count"),
        pytest.param("3", 7, id="text-is-not-a-count"),
        pytest.param(3.0, 7, id="float-is-not-a-count"),
        pytest.param(0, 0, id="zero-retained"),
        pytest.param(3, 3, id="positive-retained"),
    )

    @pytest.fixture
    def summary(self, value):
        return {"records_read": value}

    @pytest.mark.parametrize(("value", "expected"), cases)
    def test_only_nonnegative_integers_become_durable_counts(self, summary, expected):
        assert count_summary_records(summary, "records_read", 7) == expected

    @pytest.fixture
    def empty_summary(self):
        return {}

    def test_missing_count_uses_the_supplied_default(self, empty_summary):
        assert count_summary_records(empty_summary, "records_read", 7) == 7


class TestStatKindBoundary:
    @pytest.fixture(
        params=[
            pytest.param("unknown", id="unsupported-kind"),
            pytest.param("SKATER", id="wrong-case"),
            pytest.param("", id="empty-kind"),
        ]
    )
    def kind(self, request):
        return request.param

    @pytest.fixture
    def row(self):
        return {}

    def test_unknown_kind_is_not_interpreted_as_goalie(self, kind, row):
        with pytest.raises(PlayerKindViolation) as failure:
            ingestion.validate_stat_invariants(kind, row, source="fixture")
        assert failure.value.kind == kind
        assert isinstance(failure.value.__cause__, ValueError)


def test_season_and_ordered_team_helpers():
    assert ingestion._season_start_year(date(2026, 6, 30)) == 2025
    assert ingestion._season_start_year(date(2026, 7, 1)) == 2026
    assert source_utils.order_team_abbreviations("COL,CAR,DAL") == (
        "COL",
        "CAR",
        "DAL",
    )
    assert source_utils.order_team_abbreviations(" TOT, bad value,NYR ") == ("NYR",)


def test_csv_parser_rejects_duplicate_columns_and_extra_values():
    with pytest.raises(
        ingestion.IngestionValidationError, match="duplicate CSV columns"
    ):
        source_utils.parse_csv("playerId,playerId\n1,2\n", source="fixture")

    with pytest.raises(ingestion.IngestionValidationError, match="too many values"):
        source_utils.parse_csv("playerId,season\n1,2025,extra\n", source="fixture")


class TestRequiredFieldsAndSeasonTypeValidation:
    cases = [
        pytest.param(None, id="missing"),
        pytest.param("", id="empty"),
        pytest.param("  ", id="whitespace"),
        pytest.param("twenty", id="non-numeric"),
        pytest.param("2025.5", id="fractional"),
        pytest.param("0", id="zero"),
        pytest.param("Infinity", id="nonfinite"),
    ]

    @pytest.fixture(params=cases)
    def scenario(self, request):
        season = request.param
        row = {"playerId": "1", "season": season, "name": "A Player"}
        return row

    def test_required_fields_and_season_type_validation(self, scenario):
        row = scenario
        with pytest.raises(ingestion.IngestionValidationError):
            ingestion.validate_and_deduplicate_rows(
                [row],
                source="fixture",
                required_fields=("playerId", "season", "name"),
                grain_fields=("playerId", "season"),
            )


@pytest.fixture
def empty_validation_rows():
    return []


@pytest.fixture
def fractional_games_rows():
    return [
        {
            "playerId": "1",
            "season": "2025",
            "name": "A Player",
            "games_played": "10.5",
        }
    ]


@pytest.fixture
def missing_name_rows():
    return [{"playerId": "1", "season": "2025"}]


def test_validation_rejects_empty_inputs_and_schema_drift(
    empty_validation_rows, fractional_games_rows, missing_name_rows
):
    with pytest.raises(ingestion.IngestionValidationError, match="no rows"):
        ingestion.validate_and_deduplicate_rows(
            empty_validation_rows,
            source="fixture",
            required_fields=("playerId",),
            grain_fields=("playerId",),
        )

    with pytest.raises(
        ingestion.IngestionValidationError, match="games_played must be"
    ):
        ingestion.validate_and_deduplicate_rows(
            fractional_games_rows,
            source="fixture",
            required_fields=("playerId", "season", "name", "games_played"),
            grain_fields=("playerId", "season"),
            integer_fields=("playerId", "season", "games_played"),
        )
    with pytest.raises(
        ingestion.IngestionValidationError, match="missing required columns: name"
    ):
        ingestion.validate_and_deduplicate_rows(
            missing_name_rows,
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


class TestValueCoercionContractMoneyAndCapwagesPlayerParsing:
    @pytest.fixture
    def capwages_row(self):
        row = ["Fixture Player", None, "AAA", "L"] + [None] * 27
        row[7] = "CAN"
        row[30] = "97-1-13"
        return row

    def test_value_coercion_contract_money_and_capwages_player_parsing(
        self, capwages_row
    ):
        assert source_utils.parse_number("12.75") == 12.75
        assert source_utils.parse_number("12", integer=True) == 12
        assert source_utils.parse_number("NaN") is None
        assert source_utils.parse_number("bad") is None
        assert ingestion.parse_legacy_money_cents("$1,234.56") == 123456
        with pytest.raises(MoneyParseError):
            ingestion.parse_legacy_money_cents("bad")
        assert parse_capwages_birth_date("97-1-13") == "1997-01-13"
        assert parse_capwages_birth_date("97-99-13") is None

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


@pytest.fixture
def inconsistent_skater_row():
    return {"playerId": 1, "goals": 2, "assists": 3, "points": 99}


@pytest.fixture
def inconsistent_goalie_row():
    return {"playerId": 2, "shotsAgainst": 20, "saves": 18, "goalsAgainst": 3}


def test_cross_field_stat_invariants_reject_inconsistent_rows(
    inconsistent_skater_row, inconsistent_goalie_row
):
    with pytest.raises(ingestion.IngestionValidationError, match="points must equal"):
        ingestion.validate_stat_invariants(
            "skater",
            inconsistent_skater_row,
            source="fixture",
        )
    with pytest.raises(ingestion.IngestionValidationError, match="shotsAgainst"):
        ingestion.validate_stat_invariants(
            "goalie",
            inconsistent_goalie_row,
            source="fixture",
        )


class TestNhlApiParserRejectsSchemaDrift:
    @pytest.fixture
    def malformed_page(self):
        return SavedJsonSession(payload={"data": {"not": "a list"}})

    @pytest.fixture
    def missing_id_page(self):
        return SavedJsonSession(payload={"data": [{"goals": 1}]})

    def test_nhl_api_parser_rejects_schema_drift(self, malformed_page, missing_id_page):
        session = malformed_page
        with pytest.raises(
            ingestion.IngestionValidationError, match="data must be a list"
        ):
            ingestion.fetch_nhl_stats_pages(session, "skater", 2025, 2)

        session = missing_id_page
        with pytest.raises(
            ingestion.IngestionValidationError, match="missing playerId"
        ):
            ingestion.fetch_nhl_stats_pages(session, "skater", 2025, 2)


class TestRetainedSnapshots:
    expected = (
        ("players", 600),
        ("contracts", 500),
        ("contract_seasons", 900),
        ("cached", 1),
    )
    historical = (
        ("total_player_seasons", 100),
        ("covered_player_seasons", 100),
        ("missing_player_seasons", 0),
        ("cached", 1),
    )

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
                "load_capwages_summary",
                StageOutcome(
                    result=dict(self.expected), name="active-cache", events=events
                ),
            ),
            (
                capspace,
                "ingest_historical_contracts",
                StageOutcome(
                    result=dict(self.historical),
                    failure=RuntimeError("CapSpace down")
                    if request.param == "historical"
                    else None,
                    name="historical",
                    events=events,
                ),
            ),
            (
                capspace,
                "load_historical_contract_summary",
                StageOutcome(
                    result=dict(self.historical), name="historical-cache", events=events
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
        return RetainedStageScenario(failed_stage=request.param, events=events)

    def test_only_contract_failures_can_retain_the_last_good_snapshot(self, stages):
        if stages.failed_stage == "moneypuck":
            with pytest.raises(RuntimeError, match="bad stats"):
                ingestion.run_all()
            assert stages.events == ["init", "session", "moneypuck"]
            return
        result = ingestion.run_all()
        assert result["historical_contracts"] == dict(self.historical)
        assert result["schedule"] == {"games": 10}
        if stages.failed_stage == "capwages":
            assert result["capwages"] == dict(self.expected)
            assert "active-cache" in stages.events
        if stages.failed_stage == "historical":
            assert "historical-cache" in stages.events


@pytest.mark.usefixtures("isolate_command_logging")
class TestRosterCommandStatuses:
    summary = (
        ("statuses_updated", 1),
        ("active_count", 1),
        ("minors_count", 0),
        ("ltir_count", 0),
        ("unknown_count", 0),
        ("preserved_count", 0),
    )

    @pytest.fixture(
        params=[
            pytest.param(("complete", 0), id="complete"),
            pytest.param(("incomplete", 2), id="incomplete"),
            pytest.param(("failed", 1), id="failed"),
        ]
    )
    def status(self, request, monkeypatch):
        mode, status = request.param
        failure = None
        if mode == "incomplete":
            failure = populate_roster_status.IncompleteRosterFeedError(
                errors=("partial",)
            )
        if mode == "failed":
            failure = RuntimeError("database unavailable")
        monkeypatch.setattr(
            populate_roster_status, "init_db", StageOutcome(result=None)
        )
        monkeypatch.setattr(
            populate_roster_status,
            "sync_roster_status",
            StageOutcome(result=dict(self.summary), failure=failure),
        )
        return status

    def test_roster_command_exit_codes(self, status):
        assert populate_roster_status.main([]) == status


class TestMoneypuckIngestionIsIdempotentDeduplicatedAndUpdatesTypedValues:
    expected_common = (
        ("players", 2),
        ("skater", 2),
        ("goalie", 2),
        ("records_read", 5),
        ("records_skipped", 1),
        ("reconciliation_policy", "retain_missing"),
    )

    @pytest.fixture
    def expected(self):
        return dict(self.expected_common)

    @pytest.fixture
    def scenario(self):
        options: MoneyPuckFixtureOptions = {
            "expected_seasons": (2024, 2025),
            "minimum_rows_per_kind": 2,
            "maximum_duplicate_ratio": 0.5,
        }
        return options

    @pytest.fixture
    def initial_session(self):
        return MoneyPuckSession(skater_games=12)

    @pytest.fixture
    def updated_session(self):
        return MoneyPuckSession(skater_games=15)

    @pytest.mark.integration
    def test_moneypuck_ingestion_is_idempotent_deduplicated_and_updates_typed_values(
        self, scenario, migrated_database, initial_session, updated_session, expected
    ):
        options = scenario
        first = ingestion.ingest_moneypuck(initial_session, **options)
        second = ingestion.ingest_moneypuck(updated_session, **options)
        assert {key: first[key] for key in expected} == expected
        assert {key: second[key] for key in expected} == expected
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


class TestSetBasedTeamStintBackfillIsIdempotent:
    @pytest.fixture
    def source_session(self):
        return MoneyPuckSession()

    @pytest.fixture
    def backfill_connection(self, migrated_database, disposable_database_url):
        settings = DatabaseSettings(
            environment=AppEnvironment.DEV, database_url=disposable_database_url
        )
        with open_database_transaction(settings) as connection:
            yield connection

    @pytest.mark.integration
    def test_set_based_team_stint_backfill_is_idempotent(
        self, migrated_database, backfill_connection, source_session
    ):

        ingestion.ingest_moneypuck(
            source_session,
            expected_seasons=(2024, 2025),
            minimum_rows_per_kind=2,
            maximum_duplicate_ratio=0.5,
        )

        assert team_stints.plan_team_stint_backfill(backfill_connection) == {
            "canonical_assignments": 4,
            "missing_assignments": 4,
        }
        assert team_stints.apply_team_stint_backfill(backfill_connection) == {
            "canonical_assignments": 4,
            "missing_assignments": 4,
            "inserted_assignments": 4,
        }
        backfill_connection.commit()
        assert team_stints.apply_team_stint_backfill(backfill_connection) == {
            "canonical_assignments": 4,
            "missing_assignments": 0,
            "inserted_assignments": 0,
        }
        backfill_connection.commit()

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


class TestFailedIngestionRollsBackPlayersTeamsAndStats:
    @pytest.fixture
    def source_session(self):
        return MoneyPuckSession(season=2199)

    @pytest.mark.integration
    def test_failed_ingestion_rolls_back_players_teams_and_stats(
        self, migrated_database, source_session
    ):

        with pytest.raises(lookup("23503")):
            ingestion.ingest_moneypuck(
                source_session,
                expected_seasons=(2024, 2199),
                minimum_rows_per_kind=2,
                maximum_duplicate_ratio=0.5,
            )
        with migrated_database.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM players")).scalar_one()
                == 0
            )
            assert (
                connection.execute(text("SELECT count(*) FROM teams")).scalar_one() == 0
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM skater_advanced_season_stats")
                ).scalar_one()
                == 0
            )


class TestContractAndSalaryCapIngestionIsIdempotentAndUpserts:
    expected_common = (
        ("players", 1),
        ("contracts", 1),
        ("contract_seasons", 1),
        ("profile_failures", 0),
        ("records_read", 3),
        ("records_skipped", 0),
        ("reconciliation_policy", "retain_missing"),
    )

    @pytest.fixture
    def expected(self):
        return dict(self.expected_common)

    @pytest.fixture
    def initial_session(self):
        return CapWagesSession()

    @pytest.fixture
    def updated_session(self):
        return CapWagesSession(cap_hit="$1,250,000")

    @pytest.mark.integration
    def test_contract_and_salary_cap_ingestion_is_idempotent_and_upserts(
        self, migrated_database, initial_session, updated_session, expected
    ):

        first = ingestion.ingest_capwages(initial_session, minimum_players=1)
        second = ingestion.ingest_capwages(updated_session, minimum_players=1)
        assert {key: first[key] for key in expected} == expected
        assert {key: second[key] for key in expected} == expected
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


class TestPartialContractProfileRefreshIsRejectedBeforeDatabaseWrites:
    @pytest.fixture
    def failed_session(self):
        return CapWagesSession(fail_profile=True)

    @pytest.mark.integration
    def test_partial_contract_profile_refresh_is_rejected_before_database_writes(
        self, migrated_database, failed_session
    ):

        with pytest.raises(
            ingestion.IngestionValidationError, match="refusing partial refresh"
        ):
            ingestion.ingest_capwages(
                failed_session,
                minimum_players=1,
                minimum_profile_success_ratio=1.0,
            )
        with migrated_database.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM contracts")).scalar_one()
                == 0
            )
            run = connection.execute(
                text("""
                SELECT status, error_message FROM ingestion_runs
                WHERE job_name='ingest_capwages' ORDER BY id DESC LIMIT 1
            """)
            ).one()
            assert run[0] == "failed"
            assert "refusing partial refresh" in run[1]


class TestContractRejectsNoncontiguousYearsAndImpossibleCapHit:
    @pytest.fixture
    def gap_session(self):
        return InvalidContractSession(mode="gap")

    @pytest.fixture
    def cap_session(self):
        return InvalidContractSession(mode="cap")

    @pytest.mark.integration
    def test_contract_rejects_noncontiguous_years_and_impossible_cap_hit(
        self, migrated_database, gap_session, cap_session
    ):

        with pytest.raises(ingestion.IngestionValidationError, match="non-contiguous"):
            ingestion.ingest_capwages(gap_session, minimum_players=1)
        with pytest.raises(
            ingestion.IngestionValidationError, match="exceeds the season salary cap"
        ):
            ingestion.ingest_capwages(cap_session, minimum_players=1)
        with migrated_database.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM contracts")).scalar_one()
                == 0
            )


class TestNhlStatsAreDeduplicatedIdempotentAndRetainMissingRows:
    expected_common = (
        ("skater", 2),
        ("goalie", 2),
        ("records_read", 8),
        ("records_skipped", 4),
        ("reconciliation_policy", "retain_missing"),
    )

    @pytest.fixture
    def expected(self):
        return dict(self.expected_common)

    @pytest.fixture
    def initial_factory(self):
        return FixtureStatsFactory(goals=5)

    @pytest.fixture
    def updated_factory(self):
        return FixtureStatsFactory(goals=8)

    @pytest.mark.integration
    def test_nhl_stats_are_deduplicated_idempotent_and_retain_missing_rows(
        self, migrated_database, initial_factory, updated_factory, expected
    ):

        first = ingestion.ingest_nhl_stats(
            first_season=2025, last_season=2025, client_factory=initial_factory
        )
        second = ingestion.ingest_nhl_stats(
            first_season=2025, last_season=2025, client_factory=updated_factory
        )
        assert {key: first[key] for key in expected} == expected
        assert {key: second[key] for key in expected} == expected
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


class TestNhlRosterLoaderEnforcesCompletenessAndUpserts:
    @pytest.fixture
    def incomplete_session(self):
        return NhlRosterSession()

    @pytest.fixture
    def initial_session(self):
        return NhlRosterSession()

    @pytest.fixture
    def repeated_session(self):
        return NhlRosterSession()

    @pytest.mark.integration
    def test_nhl_roster_loader_enforces_completeness_and_upserts(
        self, migrated_database, incomplete_session, initial_session, repeated_session
    ):

        with pytest.raises(ingestion.IngestionValidationError, match="minimum is 2"):
            ingestion.ingest_nhl_rosters(
                incomplete_session, minimum_teams=2, minimum_active_players=1
            )
        first = ingestion.ingest_nhl_rosters(
            initial_session, minimum_teams=1, minimum_active_players=1
        )
        second = ingestion.ingest_nhl_rosters(
            repeated_session, minimum_teams=1, minimum_active_players=1
        )
        assert first == second == {"teams": 1, "active_players": 1}
        with migrated_database.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM players")).scalar_one()
                == 1
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


class TestScheduleUpsertRetainsGamesMissingFromALaterSnapshot:
    @pytest.fixture
    def initial_session(self):
        return ScheduleSession()

    @pytest.fixture
    def later_session(self):
        return ScheduleSession(game_ids=(2025020001,))

    @pytest.mark.integration
    def test_schedule_upsert_retains_games_missing_from_a_later_snapshot(
        self, migrated_database, initial_session, later_session
    ):

        first = ingestion.ingest_schedule(initial_session, season=2025, minimum_games=1)
        second = ingestion.ingest_schedule(later_session, season=2025, minimum_games=1)
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
            assert (
                connection.execute(text("SELECT count(*) FROM games")).scalar_one() == 2
            )


class TestCrossSourceIdentityUsesExternalIdAndAvoidsAmbiguousNames:
    @pytest.fixture
    def scenario(self):
        options: MoneyPuckFixtureOptions = {
            "expected_seasons": (2024, 2025),
            "minimum_rows_per_kind": 2,
            "maximum_duplicate_ratio": 0.5,
        }
        return options

    @pytest.fixture
    def puck_session(self):
        return MoneyPuckSession()

    @pytest.fixture
    def nhl_factory(self):
        return FixtureStatsFactory(goals=5)

    @pytest.fixture
    def contract_session(self):
        return CapWagesSession(player_name="Fixture Skater")

    @pytest.fixture
    def ambiguous_identity_database(
        self, scenario, migrated_database, puck_session, nhl_factory
    ):
        options = scenario
        ingestion.ingest_moneypuck(puck_session, **options)
        ingestion.ingest_nhl_stats(
            first_season=2025,
            last_season=2025,
            client_factory=nhl_factory,
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

        return migrated_database

    @pytest.mark.integration
    def test_cross_source_identity_uses_external_id_and_avoids_ambiguous_names(
        self, ambiguous_identity_database, contract_session
    ):
        ingestion.ingest_capwages(contract_session, minimum_players=1)
        with ambiguous_identity_database.connect() as connection:
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


class TestIngestionRunTrackingAndConcurrentRunLock:
    @pytest.fixture
    def fixture_stage(self):
        @ingestion_tracking.tracked_ingestion("nhl", "overlap_fixture")
        def stage():
            return {"rows": 1}

        return stage

    @pytest.fixture
    def lock_connection(self, migrated_database, disposable_database_url):
        settings = DatabaseSettings(
            environment=AppEnvironment.DEV, database_url=disposable_database_url
        )
        with open_database_transaction(settings) as connection:
            with open_database_cursor(connection) as cursor:
                cursor.execute(
                    "SELECT pg_advisory_lock(%s)",
                    (ingestion_tracking.advisory_lock_key("overlap_fixture"),),
                )
            connection.commit()
            yield connection

    @pytest.mark.integration
    def test_ingestion_run_tracking_and_concurrent_run_lock(
        self, migrated_database, fixture_stage, lock_connection
    ):
        with pytest.raises(
            ingestion_tracking.ConcurrentIngestionError, match="already running"
        ):
            fixture_stage()
        with open_database_cursor(lock_connection) as cursor:
            cursor.execute(
                "SELECT pg_advisory_unlock(%s)",
                (ingestion_tracking.advisory_lock_key("overlap_fixture"),),
            )
        lock_connection.commit()

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


@pytest.mark.integration
class TestRetainedMoneyPuckRows:
    @pytest.fixture
    def results(self, migrated_database, source_puck_options, source_puck_csv):
        repository = PostgresMoneyPuckRepository(
            transaction=ingestion.open_database_transaction
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
        return RetainedMoneyPuckScenario(
            database=migrated_database, first=first, second=second
        )

    def test_absent_stat_rows_and_external_identity_are_retained(self, results):
        assert (
            results.first.counts.records_created,
            results.second.counts.records_created,
            results.second.counts.records_updated,
        ) == (5, 0, 4)
        with results.database.connect() as connection:
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

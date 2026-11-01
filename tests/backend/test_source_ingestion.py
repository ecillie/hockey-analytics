"""Typed ingestion stages validate before persistence and own their clients."""

from dataclasses import replace
from app.ScriptingFiles.FullDataScript.source_ingestion.tests.scenarios import (
    RepositoryStage,
    ClientStage,
    BorrowedTransport,
    WorkerStage,
)
from threading import Barrier, Lock
import json
from math import isfinite
from hypothesis import given
from app.ScriptingFiles.FullDataScript.source_ingestion.tests.strategies import (
    optional_numbers,
)
import pytest
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    PlayerKind,
    serialize_summary,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.errors import (
    IngestionValidationError,
)
from app.ScriptingFiles.FullDataScript.source_ingestion import util as source_utils
from app.ScriptingFiles.FullDataScript.source_ingestion import http as source_http
from app.ScriptingFiles.FullDataScript.source_ingestion.http import (
    SourceHttpOptions,
    SessionSourceClient,
    SynchronizedSourceClient,
)
from app.ScriptingFiles.FullDataScript.ingestion import BorrowedSourceClientFactory
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.services import (
    MoneyPuckService,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.domain import (
    NhlStatsOptions,
    StatsJob,
    NhlRosterOptions,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.services import (
    NhlStatsService,
    NhlRosterService,
    fetch_stats_pages,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.schedule.domain import (
    ScheduleOptions,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.schedule.services import (
    ScheduleService,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.tests.fakes import (
    MemorySourceClient,
    OwnedClientFactory,
    ManagedResponse,
    ManagedSession,
    ManagedSessionFactory,
    MemoryMoneyPuckRepository,
    MemoryNhlStatsRepository,
    MemoryRosterRepository,
    MemoryScheduleRepository,
)


class TestMoneyPuckBoundary:
    @pytest.fixture
    def stage(self, source_puck_options, source_puck_csv):
        repository = MemoryMoneyPuckRepository()
        client = MemorySourceClient(csv_files=source_puck_csv)
        return ClientStage(
            service=MoneyPuckService(
                client=client, repository=repository, options=source_puck_options
            ),
            repository=repository,
            client=client,
        )

    def test_last_snapshot_wins_and_values_are_normalized_before_writes(self, stage):
        service, repository, client = stage.service, stage.repository, stage.client
        assert len(client) == 0
        result = service.ingest()
        assert serialize_summary(result) == {
            "players": 2,
            "skater": 2,
            "goalie": 2,
            "records_read": 5,
            "records_created": 4,
            "records_updated": 0,
            "records_skipped": 1,
            "reconciliation_policy": "retain_missing",
        }
        assert len(repository.snapshots) == 1
        rows = repository.snapshots[0].rows
        current = next(
            row for row in rows if row.kind == PlayerKind.SKATER and row.season == 2025
        )
        assert current.metrics[0] == 15
        assert current.metrics[1] == 1500
        assert current.teams == ("AAA",)
        assert current.extra_metrics_json is not None
        assert json.loads(current.extra_metrics_json)["gameScore"] == 6.5

    @pytest.fixture(
        params=[
            pytest.param("missing-season", id="historical-coverage"),
            pytest.param("duplicate-ratio", id="duplicate-ratio"),
            pytest.param("required-column", id="required-column"),
            pytest.param("negative-time", id="negative-ice-time"),
            pytest.param("fractional-games", id="fractional-games"),
        ]
    )
    def invalid_stage(self, request, source_puck_options, source_puck_csv):
        options = source_puck_options
        if request.param == "missing-season":
            options = replace(options, expected_seasons=(2023, 2024, 2025))
        if request.param == "duplicate-ratio":
            options = replace(options, maximum_duplicate_ratio=0.01)
        if request.param == "required-column":
            options.skater_file.write_text("bad_column\ninvalid\n")
        if request.param == "negative-time":
            source_puck_csv[options.skater_url] = source_puck_csv[
                options.skater_url
            ].replace("1500", "-1500")
        if request.param == "fractional-games":
            source_puck_csv[options.skater_url] = source_puck_csv[
                options.skater_url
            ].replace(",15,", ",15.5,")
        repository = MemoryMoneyPuckRepository()
        return RepositoryStage(
            service=MoneyPuckService(
                client=MemorySourceClient(csv_files=source_puck_csv),
                repository=repository,
                options=options,
            ),
            repository=repository,
        )

    def test_invalid_snapshots_never_reach_the_repository(self, invalid_stage):
        service, repository = invalid_stage.service, invalid_stage.repository
        with pytest.raises(IngestionValidationError):
            service.ingest()
        assert repository.snapshots == []


class TestStatsPagination:
    url = "https://api.nhle.com/stats/rest/en/skater/summary"

    @pytest.fixture
    def job(self):
        return StatsJob(kind=PlayerKind.SKATER, season=2025, game_type=2)

    @pytest.fixture
    def exhausted(self, source_stat_row):
        pages = {
            (self.url, 0): {"data": [source_stat_row, source_stat_row]},
            (self.url, 2): {"data": []},
        }
        return MemorySourceClient(pages=pages)

    @pytest.fixture
    def total_exhausted(self, source_stat_row):
        pages = {
            (self.url, 0): {"data": [source_stat_row], "total": 2},
            (self.url, 1): {"data": [source_stat_row], "total": 2},
        }
        return MemorySourceClient(pages=pages)

    def test_legacy_endpoint_exhausts_on_an_empty_page(self, exhausted, job):
        assert len(fetch_stats_pages(exhausted, job, page_size=2)) == 2
        assert exhausted.calls == [(self.url, 0), (self.url, 2)]

    def test_total_controls_short_pages_without_an_extra_request(
        self, total_exhausted, job
    ):
        assert len(fetch_stats_pages(total_exhausted, job, page_size=2)) == 2
        assert total_exhausted.calls == [(self.url, 0), (self.url, 1)]

    @pytest.fixture(
        params=[
            pytest.param("negative-total", id="negative-total"),
            pytest.param("string-total", id="noninteger-total"),
            pytest.param("changed-total", id="changing-total"),
            pytest.param("early-empty", id="empty-before-total"),
            pytest.param("overflow", id="rows-exceed-total"),
            pytest.param("limit", id="bounded-page-count"),
        ]
    )
    def malformed(self, request, source_stat_row):
        first = {"data": [source_stat_row, source_stat_row], "total": 4}
        second = {"data": [source_stat_row, source_stat_row], "total": 4}
        maximum_pages = 2
        if request.param == "negative-total":
            first["total"] = -1
        if request.param == "string-total":
            first["total"] = "4"
        if request.param == "changed-total":
            second["total"] = 5
        if request.param == "early-empty":
            second["data"] = []
        if request.param == "overflow":
            first["total"] = 1
        if request.param == "limit":
            first["total"] = 8
            second["total"] = 8
        return MemorySourceClient(
            pages={(self.url, 0): first, (self.url, 2): second}
        ), maximum_pages

    def test_malformed_metadata_cannot_return_a_partial_success(self, malformed, job):
        client, maximum = malformed
        with pytest.raises(IngestionValidationError):
            fetch_stats_pages(client, job, page_size=2, maximum_pages=maximum)


class TestNhlWorkerOwnership:
    @pytest.fixture(
        params=[
            pytest.param(False, id="successful-validation"),
            pytest.param(True, id="invariant-failure"),
        ]
    )
    def stage(self, request, source_stat_row):
        raw = dict(source_stat_row)
        if request.param:
            raw["points"] = 99
        pages = {
            (f"https://api.nhle.com/stats/rest/en/{kind}/summary", 0): {"data": [raw]}
            for kind in PlayerKind
        }
        factory = OwnedClientFactory(
            client=MemorySourceClient(pages=pages), barrier=Barrier(2)
        )
        repository = MemoryNhlStatsRepository()
        service = NhlStatsService(
            client_factory=factory,
            repository=repository,
            options=NhlStatsOptions(first_season=2025, last_season=2025, workers=2),
        )
        return WorkerStage(
            service=service,
            repository=repository,
            factory=factory,
            invalid=request.param,
        )

    def test_worker_bound_and_cleanup_on_success_or_failure(self, stage):
        service, repository, factory, invalid = (
            stage.service,
            stage.repository,
            stage.factory,
            stage.invalid,
        )
        if invalid:
            with pytest.raises(IngestionValidationError):
                service.ingest()
            assert repository.snapshots == []
        if not invalid:
            assert service.ingest().counts.records_read == 4
            assert len(repository.snapshots) == 1
        assert factory.state == {"opened": 4, "active": 0, "maximum": 2, "closed": 4}


class TestScheduleValidation:
    @pytest.fixture
    def stage(self, source_schedule_page):
        repository = MemoryScheduleRepository()
        client = MemorySourceClient(
            pages={
                (
                    "https://api-web.nhle.com/v1/schedule/2025-10-01",
                    0,
                ): source_schedule_page
            }
        )
        return RepositoryStage(
            service=ScheduleService(
                client=client,
                repository=repository,
                options=ScheduleOptions(season=2025, minimum_games=1),
            ),
            repository=repository,
        )

    def test_schedule_is_normalized_before_upsert(self, stage):
        service, repository = stage.service, stage.repository
        result = service.ingest()
        assert result.games == 1
        assert repository.snapshots[0].games[0].away_team == "AAA"
        assert repository.snapshots[0].games[0].game_date.isoformat() == "2025-10-01"

    @pytest.fixture(
        params=[
            pytest.param("missing-team", id="missing-required-team"),
            pytest.param("backward", id="nonadvancing-date"),
            pytest.param("bad-date", id="malformed-metadata-date"),
            pytest.param("few-games", id="game-count-floor"),
        ]
    )
    def invalid(self, request, source_schedule_page):
        options = ScheduleOptions(season=2025, minimum_games=1)
        if request.param == "missing-team":
            source_schedule_page["gameWeek"][0]["games"][0]["homeTeam"] = {}
        if request.param == "backward":
            source_schedule_page["nextStartDate"] = "2025-10-01"
        if request.param == "bad-date":
            source_schedule_page["nextStartDate"] = "yesterday"
        if request.param == "few-games":
            options = replace(options, minimum_games=2)
        repository = MemoryScheduleRepository()
        client = MemorySourceClient(
            pages={
                (
                    "https://api-web.nhle.com/v1/schedule/2025-10-01",
                    0,
                ): source_schedule_page
            }
        )
        return RepositoryStage(
            service=ScheduleService(
                client=client, repository=repository, options=options
            ),
            repository=repository,
        )

    def test_invalid_schedule_cannot_write(self, invalid):
        service, repository = invalid.service, invalid.repository
        with pytest.raises(IngestionValidationError):
            service.ingest()
        assert repository.snapshots == []


class TestRosterValidation:
    @pytest.fixture
    def stage(self):
        repository = MemoryRosterRepository()
        client = MemorySourceClient(
            pages={
                ("https://api-web.nhle.com/v1/standings/now", 0): {
                    "standings": [{"teamAbbrev": {"default": "AAA"}}]
                },
                ("https://api-web.nhle.com/v1/roster/AAA/current", 0): {
                    "forwards": [{"id": 1}],
                    "defensemen": [],
                    "goalies": [],
                },
            }
        )
        return RepositoryStage(
            service=NhlRosterService(
                client=client,
                repository=repository,
                options=NhlRosterOptions(
                    season=2025, minimum_teams=1, minimum_active_players=2
                ),
            ),
            repository=repository,
        )

    def test_insufficient_active_roster_is_rejected_before_identity_writes(self, stage):
        service, repository = stage.service, stage.repository
        with pytest.raises(IngestionValidationError):
            service.ingest()
        assert repository.snapshots == []


class TestOwnedHttpTransport:
    @pytest.fixture
    def options(self):
        return SourceHttpOptions(json_timeout=2, csv_timeout=3)

    @pytest.fixture(
        params=[
            pytest.param(False, id="success"),
            pytest.param(True, id="request-failure"),
        ]
    )
    def session(self, request, monkeypatch):
        response = ManagedResponse(
            payload={"ok": True},
            failure=RuntimeError("source unavailable") if request.param else None,
        )
        session = ManagedSession(response=response)
        monkeypatch.setattr(
            source_http, "http_session", ManagedSessionFactory(session=session)
        )
        return session, request.param

    def test_owned_session_closes_on_success_and_source_failure(self, session, options):
        resource, failing = session
        if failing:
            with pytest.raises(RuntimeError, match="source unavailable"):
                with source_http.open_source_client(options) as client:
                    client.get_json("https://source.test")
        if not failing:
            with source_http.open_source_client(options) as client:
                assert client.get_json("https://source.test") == {"ok": True}
                assert client.get_csv("https://source.test/file.csv") == "csv-content"
            assert resource.calls[-1][1] == 3
        assert resource.calls[0][1] == 2
        assert resource.opened == resource.closed == [True]


class TestInvalidQualityOptions:
    @pytest.fixture(
        params=[
            pytest.param(float("nan"), id="nan-ratio"),
            pytest.param(float("inf"), id="infinite-ratio"),
            pytest.param(-1.0, id="negative-ratio"),
            pytest.param(1.5, id="ratio-above-one"),
        ]
    )
    def stage(self, request, source_puck_options, source_puck_csv):
        options = replace(source_puck_options, maximum_duplicate_ratio=request.param)
        client = MemorySourceClient(csv_files=source_puck_csv)
        repository = MemoryMoneyPuckRepository()
        return ClientStage(
            service=MoneyPuckService(
                client=client, repository=repository, options=options
            ),
            repository=repository,
            client=client,
        )

    def test_invalid_options_fail_before_fetching_or_writing(self, stage):
        service, repository, client = stage.service, stage.repository, stage.client
        with pytest.raises(IngestionValidationError):
            service.ingest()
        assert repository.snapshots == []
        assert client.calls == []


class TestOptionalNumericParsing:
    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("NaN", id="nan"),
            pytest.param("Infinity", id="infinity"),
            pytest.param("1e9999", id="finite-decimal-overflows-float"),
        ],
    )
    def test_unrepresentable_optional_values_remain_missing(self, value):
        assert source_utils.parse_number(value) is None


@given(optional_numbers())
def test_optional_decimal_values_are_finite_or_missing(value):
    result = source_utils.parse_number(value)
    assert result is None or isfinite(result)


class TestLocalizedScheduleNormalization:
    @pytest.fixture
    def stage(self, source_schedule_page):
        source_schedule_page["gameWeek"][0]["games"][0]["venue"] = {
            "fr": "Fixture Arena"
        }
        source_schedule_page["gameWeek"][0]["games"][0]["awayTeam"]["abbrev"] = " aaa "
        repository = MemoryScheduleRepository()
        client = MemorySourceClient(
            pages={
                (
                    "https://api-web.nhle.com/v1/schedule/2025-10-01",
                    0,
                ): source_schedule_page
            }
        )
        return RepositoryStage(
            service=ScheduleService(
                client=client,
                repository=repository,
                options=ScheduleOptions(season=2025, minimum_games=1),
            ),
            repository=repository,
        )

    def test_localized_fallback_and_team_normalization_preserve_input(
        self, stage, source_schedule_page
    ):
        service, repository = stage.service, stage.repository
        service.ingest()
        game = repository.snapshots[0].games[0]
        assert (game.away_team, game.venue) == ("AAA", "Fixture Arena")
        original = source_schedule_page["gameWeek"][0]["games"][0]
        assert original["awayTeam"]["abbrev"] == " aaa "
        assert "_game_date" not in original


class TestBorrowedTransport:
    @pytest.fixture
    def transport(self):
        lock = Lock()
        session = ManagedSession(
            response=ManagedResponse(payload={"ok": True}), required_lock=lock
        )
        client = SynchronizedSourceClient(
            client=SessionSourceClient(session=session), lock=lock
        )
        return BorrowedTransport(
            factory=BorrowedSourceClientFactory(client=client), session=session
        )

    def test_borrowed_requests_are_guarded_without_taking_session_ownership(
        self, transport
    ):
        factory, session = transport.factory, transport.session
        with factory() as client:
            assert client.get_json("https://source.test") == {"ok": True}
            assert client.get_csv("https://source.test/file.csv") == "csv-content"
        assert session.calls == [
            ("https://source.test", 30),
            ("https://source.test/file.csv", 60),
        ]
        assert session.opened == session.closed == []


class TestProductionRetryConfiguration:
    def test_existing_get_retry_and_backoff_policy_is_preserved(self):
        with source_http.http_session() as session:
            retry = session.get_adapter("https://").max_retries
            assert retry.total == 4
            assert retry.backoff_factor == 0.6
            assert retry.status_forcelist == (429, 500, 502, 503, 504)
            assert retry.allowed_methods == ("GET",)
            assert retry.respect_retry_after_header


class TestInvalidMinimumRows:
    @pytest.fixture
    def stage(self, source_puck_options):
        options = replace(source_puck_options, minimum_rows_per_kind=-1)
        client = MemorySourceClient()
        repository = MemoryMoneyPuckRepository()
        return ClientStage(
            service=MoneyPuckService(
                client=client, repository=repository, options=options
            ),
            repository=repository,
            client=client,
        )

    def test_negative_minimum_fails_before_fetching_or_writing(self, stage):
        with pytest.raises(IngestionValidationError):
            stage.service.ingest()
        assert stage.client.calls == []
        assert stage.repository.snapshots == []

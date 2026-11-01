"""Typed ingestion stages validate before persistence and own their clients."""

from dataclasses import replace
import asyncio
import requests
from app.shared.tests.fakes import StageOutcome
from copy import deepcopy
from pydantic import TypeAdapter, ValidationError
from app.ScriptingFiles.FullDataScript.source_ingestion.schemas import (
    Integer,
    SchedulePage,
    StatsPage,
    TeamAbbreviation,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.tests.scenarios import (
    RepositoryStage,
    ClientStage,
    BorrowedTransport,
    WorkerStage,
    PaginationScenario,
    SessionScenario,
    SessionSetupScenario,
    SessionCloseProbe,
    SessionLifetimeScenario,
    exercise_session_owner,
    ValidationBoundary,
)
from threading import Barrier, Lock
import json
from math import isfinite
from hypothesis import given
from app.ScriptingFiles.FullDataScript.source_ingestion.tests.strategies import (
    generate_optional_numbers,
)
import pytest
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    PlayerKind,
    serialize_summary,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.errors import (
    IngestionValidationError,
    IntegerValueViolation,
    TeamAbbreviationViolation,
    OptionsViolation,
)
from app.ScriptingFiles.FullDataScript.source_ingestion import util as source_utils
from app.ScriptingFiles.FullDataScript.source_ingestion.repository import (
    http as source_http,
)
from app.ScriptingFiles.FullDataScript.contracts.repository import http as profile_http
from app.ScriptingFiles.FullDataScript.source_ingestion.repository.http import (
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
    parse_schedule_page,
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
        return PaginationScenario(
            client=MemorySourceClient(
                pages={(self.url, 0): first, (self.url, 2): second}
            ),
            maximum_pages=maximum_pages,
        )

    def test_malformed_metadata_cannot_return_a_partial_success(self, malformed, job):
        with pytest.raises(IngestionValidationError):
            fetch_stats_pages(
                malformed.client,
                job,
                page_size=2,
                maximum_pages=malformed.maximum_pages,
            )


class TestNhlOptionsBeforeResources:
    cases = (
        pytest.param(("first_season", 2026), id="unordered-seasons"),
        pytest.param(("workers", 0), id="zero-workers"),
        pytest.param(("page_size", 0), id="zero-page-size"),
        pytest.param(("maximum_pages", 0), id="zero-page-budget"),
    )

    @pytest.fixture(params=cases)
    def stage(self, request):
        field, value = request.param
        options = replace(
            NhlStatsOptions(first_season=2025, last_season=2025), **{field: value}
        )
        factory = OwnedClientFactory(client=MemorySourceClient(), barrier=Barrier(1))
        repository = MemoryNhlStatsRepository()
        return WorkerStage(
            service=NhlStatsService(
                client_factory=factory, repository=repository, options=options
            ),
            factory=factory,
            repository=repository,
            invalid=True,
        )

    def test_invalid_options_open_no_clients_and_write_no_snapshot(self, stage):
        with pytest.raises(OptionsViolation):
            stage.service.ingest()
        assert stage.factory.state == {}
        assert stage.repository.snapshots == []


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
            source_http, "open_http_session", ManagedSessionFactory(session=session)
        )
        return SessionScenario(session=session, failing=request.param)

    def test_owned_session_closes_on_success_and_source_failure(self, session, options):
        if session.failing:
            with pytest.raises(RuntimeError, match="source unavailable"):
                with source_http.open_source_client(options) as client:
                    client.get_json("https://source.test")
        if session.failing is False:
            with source_http.open_source_client(options) as client:
                assert client.get_json("https://source.test") == {"ok": True}
                assert client.get_csv("https://source.test/file.csv") == "csv-content"
            assert session.session.calls[-1][1] == 3
        assert session.session.calls[0][1] == 2
        assert session.session.opened == session.session.closed == [True]


class TestSessionSetupCleanup:
    @pytest.fixture(
        params=[
            pytest.param("retry", id="retry-construction"),
            pytest.param("mount", id="adapter-installation"),
            pytest.param("headers", id="header-installation"),
        ]
    )
    def operation(self, request):
        return request.param

    @pytest.fixture(
        params=[
            pytest.param(RuntimeError, id="error"),
            pytest.param(asyncio.CancelledError, id="cancelled"),
            pytest.param(KeyboardInterrupt, id="interrupted"),
        ]
    )
    def failure_kind(self, request):
        return request.param

    @pytest.fixture(
        params=[
            pytest.param(False, id="closed"),
            pytest.param(True, id="close-failed"),
        ]
    )
    def cleanup_fails(self, request):
        return request.param

    @pytest.fixture
    def scenario(self, operation, failure_kind, cleanup_fails, monkeypatch):
        with requests.Session() as session, monkeypatch.context() as patches:
            cause = ValueError("session setup cause")
            primary = failure_kind("session setup failed")
            primary.__cause__ = cause
            scenario = SessionSetupScenario(
                resource=SessionCloseProbe(
                    session=session,
                    native_close=session.close,
                    cleanup=RuntimeError("session close failed")
                    if cleanup_fails
                    else None,
                    closed=[],
                ),
                primary=primary,
                cause=cause,
            )
            patches.setattr(
                source_http.requests, "Session", StageOutcome(result=session)
            )
            patches.setattr(session, "close", scenario.resource.close)
            rejected = StageOutcome(result=None, failure=primary)
            if operation == "retry":
                patches.setattr(source_http, "Retry", rejected)
            if operation == "mount":
                patches.setattr(session, "mount", rejected)
            if operation == "headers":
                patches.setattr(session.headers, "update", rejected)
            yield scenario

    def test_setup_failure_closes_session_without_masking_primary(self, scenario):
        with pytest.raises(type(scenario.primary)) as failure:
            source_http.open_http_session()
        assert failure.value is scenario.primary
        assert failure.value.__cause__ is scenario.cause
        assert scenario.resource.closed == [True]
        if scenario.resource.cleanup is not None:
            assert (
                failure.value.__dict__["tradevalue_cleanup"]
                is scenario.resource.cleanup
            )


class TestSessionLifetimeCleanup:
    failure_cases = (
        pytest.param(None, id="success"),
        pytest.param(RuntimeError, id="error"),
        pytest.param(asyncio.CancelledError, id="cancelled"),
        pytest.param(KeyboardInterrupt, id="interrupted"),
    )

    @pytest.fixture(params=failure_cases)
    def primary_kind(self, request):
        return request.param

    @pytest.fixture(params=failure_cases)
    def cleanup_kind(self, request):
        return request.param

    @pytest.fixture(
        params=[
            pytest.param("source", id="source-client"),
            pytest.param("historical", id="historical-profile"),
            pytest.param("active", id="active-profile"),
        ]
    )
    def factory(self, request):
        return {
            "source": source_http.open_source_client,
            "historical": profile_http.open_profile_session,
            "active": profile_http.open_active_session,
        }[request.param]

    @pytest.fixture(
        params=[
            pytest.param(True, id="entry"),
            pytest.param(False, id="body"),
        ]
    )
    def fail_during_entry(self, request):
        return request.param

    @pytest.fixture
    def scenario(
        self, factory, primary_kind, cleanup_kind, fail_during_entry, monkeypatch
    ):
        with requests.Session() as session, monkeypatch.context() as patches:
            cause = ValueError("session lifetime cause")
            primary = (
                primary_kind("session lifetime failed")
                if primary_kind is not None
                else None
            )
            cleanup = (
                cleanup_kind("session cleanup failed")
                if cleanup_kind is not None
                else None
            )
            if primary is not None:
                primary.__cause__ = cause
            if cleanup is not None:
                cleanup.__cause__ = cause
            resource = SessionCloseProbe(
                session=session, native_close=session.close, cleanup=cleanup, closed=[]
            )
            patches.setattr(session, "close", resource.close)
            created = StageOutcome(result=session)
            patches.setattr(source_http, "open_http_session", created)
            patches.setattr(profile_http, "open_http_session", created)
            if fail_during_entry:
                patches.setattr(
                    requests.Session,
                    "__enter__",
                    StageOutcome(result=session, failure=primary),
                )
            yield SessionLifetimeScenario(
                factory=factory,
                resource=resource,
                primary=primary,
                cause=cause,
                fail_during_entry=fail_during_entry,
            )

    def test_entry_body_and_close_retain_the_correct_failure(self, scenario):
        expected = scenario.expected_failure
        if expected is None:
            exercise_session_owner(scenario)
        if expected is not None:
            with pytest.raises(BaseException) as failure:
                exercise_session_owner(scenario)
            assert failure.value is expected
            assert failure.value.__cause__ is scenario.cause
        assert scenario.resource.closed == [True]
        if scenario.primary is not None and scenario.resource.cleanup is not None:
            assert (
                scenario.primary.__dict__["tradevalue_cleanup"]
                is scenario.resource.cleanup
            )


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


@given(generate_optional_numbers())
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
    @pytest.fixture
    def session(self):
        with source_http.open_http_session() as session:
            yield session

    def test_existing_get_retry_and_backoff_policy_is_preserved(self, session):
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


class TestStatsPageSnapshots:
    @pytest.fixture
    def payload(self):
        return {"data": [{"playerId": 7, "details": {"teams": ["AAA"]}}], "total": 1}

    @pytest.fixture
    def expected(self, payload):
        return deepcopy(payload)

    @pytest.fixture
    def page(self, payload):
        return StatsPage.model_validate(payload)

    def test_input_aliases_cannot_change_validated_rows(self, page, payload, expected):
        payload["data"][0]["details"]["teams"].append("BBB")
        assert page.model_dump(mode="json") == expected

    def test_returned_rows_are_detached(self, page, expected):
        rows = page.data
        rows[0]["details"]["teams"].append("BBB")
        rows[0]["playerId"] = 8
        assert page.model_dump(mode="json") == expected
        assert page.data == tuple(expected["data"])

    def test_snapshot_storage_is_frozen(self, page):
        with pytest.raises(ValidationError, match="frozen"):
            page.data_snapshot = ()

    def test_serialization_retains_source_shape(self, page, expected):
        assert json.loads(page.model_dump_json()) == expected
        assert page.model_dump()["data"] == tuple(expected["data"])


class TestSchedulePageSnapshots:
    @pytest.fixture
    def payload(self, source_schedule_page):
        source_schedule_page["gameWeek"][0]["games"].append(
            {
                "gameType": 3,
                "id": "not-a-regular-game",
                "homeTeam": {"score": "invalid"},
            }
        )
        return source_schedule_page

    @pytest.fixture
    def expected(self, payload):
        return deepcopy(payload)

    @pytest.fixture
    def page(self, payload):
        return SchedulePage.model_validate(payload)

    def test_input_aliases_cannot_change_validated_games(self, page, payload, expected):
        payload["gameWeek"][0]["games"][0]["homeTeam"]["abbrev"] = "CCC"
        assert json.loads(page.model_dump_json()) == expected

    def test_returned_games_are_detached(self, page, expected):
        games = page.gameWeek[0].games
        games[0]["homeTeam"]["abbrev"] = "CCC"
        games[0]["id"] = 99
        assert json.loads(page.model_dump_json()) == expected
        assert page.gameWeek[0].games == tuple(expected["gameWeek"][0]["games"])

    def test_serialization_retains_source_shape(self, page, expected):
        assert json.loads(page.model_dump_json()) == expected
        assert page.model_dump()["gameWeek"][0]["games"] == tuple(
            expected["gameWeek"][0]["games"]
        )

    def test_nonregular_games_are_filtered_before_game_validation(self, page):
        games = parse_schedule_page(page, source="fixture")
        assert len(games) == 1
        assert games[0].external_id == 1


class TestTypedNativeValidatorFailures:
    cases = (
        pytest.param((Integer, IntegerValueViolation), id="finite-integer"),
        pytest.param(
            (TeamAbbreviation, TeamAbbreviationViolation), id="team-abbreviation"
        ),
    )

    @pytest.fixture(params=cases)
    def boundary(self, request):
        schema, failure = request.param
        return ValidationBoundary(adapter=TypeAdapter(schema), failure_type=failure)

    @pytest.fixture
    def value(self):
        return "input_secret"

    def test_native_validation_retains_typed_context_without_echoing_input(
        self, boundary, value
    ):
        with pytest.raises(ValidationError) as raised:
            boundary.adapter.validate_python(value)
        issue = raised.value.errors(include_input=False)[0]
        failure = issue["ctx"]["error"]
        assert isinstance(failure, boundary.failure_type)
        assert failure.value == value
        assert "input_secret" not in issue["msg"]

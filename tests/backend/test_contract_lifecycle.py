"""Contract option validation and bounded profile session ownership."""

import json
from dataclasses import replace
from pathlib import Path
from threading import Barrier, Lock
import pytest
from app.ScriptingFiles.FullDataScript import capspace, ingestion, ingestion_tracking
from app.ScriptingFiles.FullDataScript.contracts import repository as persistence
from app.ScriptingFiles.FullDataScript.contracts import services as contract_services
from app.ScriptingFiles.FullDataScript.contracts.active_repository import (
    open_active_repository,
)
from app.ScriptingFiles.FullDataScript.contracts.active_services import (
    ActiveContractService,
)
from app.ScriptingFiles.FullDataScript.contracts.domain import Candidate, StoredContract
from app.ScriptingFiles.FullDataScript.contracts.errors import ReconciliationFailure
from app.ScriptingFiles.FullDataScript.contracts.http import (
    BorrowedProfileSessionFactory,
    SynchronizedProfileSession,
    calculate_retry_delay,
)
from app.ScriptingFiles.FullDataScript.contracts.options import (
    ActiveContractOptions,
    ContractOptionError,
    HistoricalContractOptions,
    HistoricalContractLimits,
    ProfileHttpOptions,
)
from app.ScriptingFiles.FullDataScript.contracts.policy import (
    ContractReconciliationPolicy,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.contracts import (
    parse_capspace_page,
)
from app.ScriptingFiles.FullDataScript.contracts.services import (
    HistoricalContractService,
    ProfileFetcher,
)
from app.ScriptingFiles.FullDataScript.contracts.tests.fakes import (
    ActiveSessionProbe,
    FailedControlConnection,
    FailedTrackingScenario,
    EmptyContractRepository,
    FailingCleanup,
    LockObservedSession,
    ProfileSessionProbe,
    reject_resource_access,
)
from app.ScriptingFiles.FullDataScript.contracts.tests.fixtures import SavedResponse
from app.ScriptingFiles.FullDataScript.tracking.repository import (
    close_run_resources,
    open_ingestion_run,
)
from app.ScriptingFiles.FullDataScript.contracts.tests.fakes import (
    ProfileOptionScenario,
)


class TestContractOptionValidation:
    @pytest.fixture(
        params=[
            pytest.param({"workers": 0}, id="no-workers"),
            pytest.param({"workers": 9}, id="excess-workers"),
            pytest.param({"batch_size": 0}, id="no-batch"),
            pytest.param({"batch_size": 1001}, id="excess-batch"),
            pytest.param(
                {"first_season": 2026, "last_season": 2025}, id="reversed-range"
            ),
            pytest.param({"limit": 0}, id="zero-limit"),
            pytest.param({"limit": -1}, id="negative-limit"),
            pytest.param({"player_id": 0}, id="zero-player"),
            pytest.param({"nhl_id": ""}, id="empty-nhl-id"),
            pytest.param({"nhl_id": "0"}, id="zero-nhl-id"),
            pytest.param({"nhl_id": "12/3"}, id="malformed-nhl-id"),
            pytest.param({"nhl_id": "١٢٣"}, id="non-ascii-nhl-id"),
        ]
    )
    def invalid_options(self, request, monkeypatch):
        monkeypatch.setattr(
            capspace, "track_historical_contracts", reject_resource_access
        )
        monkeypatch.setattr(
            persistence, "open_contract_repository", reject_resource_access
        )
        monkeypatch.setattr(capspace, "open_profile_session", reject_resource_access)
        return request.param

    def test_apply_rejects_before_tracking(self, invalid_options):
        with pytest.raises(ContractOptionError):
            capspace.ingest_historical_contracts(**invalid_options)

    def test_preview_rejects_before_reading(self, invalid_options):
        with pytest.raises(ContractOptionError):
            capspace.preview_historical_contracts(**invalid_options)

    @pytest.fixture
    def defaults(self):
        return HistoricalContractOptions()

    def test_service_rejects_before_reading(self, invalid_options, defaults):
        with pytest.raises(ContractOptionError):
            capspace.run_historical_contracts(
                None,
                options=replace(defaults, **invalid_options),
                dry_run=False,
            )


class TestProfileSessionOwnership:
    @pytest.fixture(
        params=[
            pytest.param(0, id="zero-workers"),
            pytest.param(9, id="exceeds-default-limit"),
        ]
    )
    def rejected_workers(self, request):
        return request.param

    def test_invalid_workers_open_no_sessions(
        self, fetcher, candidates, probe, rejected_workers
    ):
        with pytest.raises(ContractOptionError):
            fetcher.fetch_profiles(tuple(candidates), rejected_workers)
        assert probe.opened == []

    @pytest.fixture
    def custom_options(self):
        return HistoricalContractOptions(
            workers=9, limits=HistoricalContractLimits(maximum_workers=9)
        )

    @pytest.fixture
    def custom_service(self, candidates, fetcher):
        repository = EmptyContractRepository(candidates=tuple(candidates))
        return HistoricalContractService(
            repository_factory=repository.open_repository, fetcher=fetcher
        )

    def test_service_uses_injected_worker_limit(
        self, custom_service, custom_options, probe
    ):
        summary = custom_service.run(custom_options, dry_run=True)
        assert summary["profiles_requested"] == 4
        assert len(probe.opened) == 4
        assert len(probe.closed) == 4

    @pytest.fixture
    def candidates(self):
        return [
            Candidate(
                player_id=player_id,
                first_name="Pavel",
                last_name="Datsyuk",
                nhl_id="8467514",
                missing_seasons=(2008, 2009),
            )
            for player_id in range(1, 5)
        ]

    @pytest.fixture
    def probe(self, monkeypatch):
        body = (
            Path(__file__)
            .parent.joinpath("fixtures", "ingestion", "capspace_datsyuk.html")
            .read_text()
        )
        probe = ProfileSessionProbe(
            response=SavedResponse(
                status_code=200,
                headers={},
                text=body,
                url="https://cap-space.com/person/nhl:8467514",
            ),
            barrier=Barrier(4),
        )
        monkeypatch.setattr(capspace, "open_profile_session", probe.open_session)
        return probe

    @pytest.fixture
    def fetcher(self, probe):
        return ProfileFetcher(session_factory=probe.open_session)

    def test_concurrent_profiles_have_distinct_closed_sessions(
        self, candidates, probe, fetcher
    ):
        results = fetcher.fetch_profiles(tuple(candidates), workers=4)

        assert len(results) == 4
        assert all(result.covers_target for result in results)
        assert len({id(session) for session in probe.opened}) == 4
        assert {id(session) for session in probe.closed} == {
            id(session) for session in probe.opened
        }

    @pytest.fixture
    def failing_fetch(self, monkeypatch):
        monkeypatch.setattr(
            contract_services, "fetch_profile_with_fallback", reject_resource_access
        )

    @pytest.mark.usefixtures("failing_fetch")
    def test_owned_session_closes_when_fetch_fails(self, candidates, probe, fetcher):
        with pytest.raises(AssertionError, match="resource boundary"):
            fetcher.fetch_profiles(tuple(candidates[:1]), workers=1)

        assert len(probe.opened) == 1
        assert probe.closed == probe.opened


class TestTrackingFailurePreservation:
    @pytest.fixture
    def scenario(self, monkeypatch):
        scenario = FailedTrackingScenario(
            primary=RuntimeError("profile batch failed"),
            reporting=RuntimeError("run update failed"),
        )
        monkeypatch.setattr(ingestion_tracking, "open_ingestion_run", scenario.open_run)
        return scenario

    @pytest.fixture
    def cleanup_operations(self):
        calls: list[str] = []
        return (
            FailingCleanup(
                failure=RuntimeError("unlock failed"), calls=calls, name="unlock"
            ),
            FailingCleanup(
                failure=RuntimeError("cursor failed"), calls=calls, name="cursor"
            ),
            FailingCleanup(
                failure=RuntimeError("close failed"), calls=calls, name="connection"
            ),
        )

    def test_reporting_failure_preserves_original_exception(self, scenario):
        ingest = ingestion_tracking.tracked_ingestion("capspace")(scenario.ingest)
        with pytest.raises(RuntimeError) as raised:
            ingest()

        assert raised.value is scenario.primary
        assert "run update failed" in raised.value.__notes__[0]

    def test_cleanup_preserves_primary_and_attempts_every_resource(
        self, scenario, cleanup_operations
    ):
        close_run_resources(cleanup_operations, scenario.primary)

        assert cleanup_operations[0].calls == ["unlock", "cursor", "connection"]
        assert len(scenario.primary.__notes__) == 3

    def test_cleanup_reports_first_failure_and_attempts_every_resource(
        self, cleanup_operations
    ):
        with pytest.raises(RuntimeError) as raised:
            close_run_resources(cleanup_operations, None)

        assert raised.value is cleanup_operations[0].failure
        assert cleanup_operations[0].calls == ["unlock", "cursor", "connection"]
        assert len(raised.value.__notes__) == 2


class TestBorrowedProfileOwnership:
    @pytest.fixture
    def borrowed(self):
        lock = Lock()
        body = (
            Path(__file__)
            .parent.joinpath("fixtures", "ingestion", "capspace_datsyuk.html")
            .read_text()
        )
        session = LockObservedSession(
            response=SavedResponse(
                status_code=200,
                headers={},
                text=body,
                url="https://cap-space.com/person/nhl:8467514",
            ),
            lock=lock,
        )
        return session

    @pytest.fixture
    def candidates(self):
        return tuple(
            Candidate(
                player_id=player_id,
                first_name="Pavel",
                last_name="Datsyuk",
                nhl_id="8467514",
                missing_seasons=(2008, 2009),
            )
            for player_id in range(4)
        )

    @pytest.fixture
    def fetcher(self, borrowed):
        factory = BorrowedProfileSessionFactory(
            session=SynchronizedProfileSession(session=borrowed, lock=borrowed.lock)
        )
        return ProfileFetcher(session_factory=factory)

    def test_borrowed_gets_are_guarded_and_owner_keeps_session(
        self, borrowed, candidates, fetcher
    ):
        results = fetcher.fetch_profiles(candidates, 4)

        assert len(results) == 4
        assert all(result.covers_target for result in results)
        assert len(borrowed.calls) == 4
        assert borrowed.closures == []


class TestControlConnectionSetupFailure:
    @pytest.fixture
    def connection(self):
        return FailedControlConnection(failure=RuntimeError("cursor setup failed"))

    def test_cursor_setup_failure_closes_connection(self, connection):
        with pytest.raises(RuntimeError) as raised:
            with open_ingestion_run(
                source_code="capspace",
                job_name="cursor-failure",
                connection_factory=connection.open_connection,
            ):
                raise AssertionError("cursor failure entered ingestion")

        assert raised.value is connection.failure
        assert connection.closures == [True]


class TestProfileRetryDelay:
    @pytest.fixture(
        params=[
            pytest.param("-1", id="negative"),
            pytest.param("NaN", id="nan"),
            pytest.param("inf", id="infinite"),
            pytest.param("bad", id="malformed"),
        ]
    )
    def invalid_retry_after(self, request):
        return SavedResponse(
            status_code=429, headers={"Retry-After": request.param}, text="", url=""
        )

    @pytest.fixture
    def default_options(self):
        return ProfileHttpOptions()

    def test_invalid_delay_uses_normal_backoff(
        self, invalid_retry_after, default_options
    ):
        assert calculate_retry_delay(invalid_retry_after, 1, default_options) == 2


class TestContractReconciliationPolicy:
    @pytest.fixture
    def incoming(self):
        body = (
            Path(__file__)
            .parent.joinpath("fixtures", "ingestion", "capspace_datsyuk.html")
            .read_text()
        )
        return parse_capspace_page(body, expected_nhl_id="8467514")[0]

    @pytest.fixture(
        params=[
            pytest.param("ambiguous", id="ambiguous-contracts"),
            pytest.param("foreign", id="foreign-player"),
            pytest.param("value", id="different-total"),
            pytest.param("team", id="different-team"),
        ]
    )
    def conflict(self, request, incoming):
        existing = StoredContract(
            contract_id=1,
            player_id=42,
            signing_team_id=900,
            total_value_cents=incoming.total_value_cents,
        )
        if request.param == "ambiguous":
            return (
                existing,
                replace(existing, contract_id=2),
            ), ReconciliationFailure.AMBIGUOUS
        if request.param == "foreign":
            return (
                replace(existing, player_id=43),
            ), ReconciliationFailure.FOREIGN_PLAYER
        if request.param == "value":
            return (
                replace(existing, total_value_cents=1),
            ), ReconciliationFailure.INCOMPATIBLE
        return (
            replace(existing, signing_team_id=901),
        ), ReconciliationFailure.INCOMPATIBLE

    @pytest.fixture
    def policy(self, incoming):
        return ContractReconciliationPolicy(
            player_id=42, incoming=incoming, signing_team_id=900
        )

    def test_conflicts_have_structured_reasons(self, conflict, policy):
        matches, reason = conflict
        violation = policy.find_violation(matches)

        assert violation is not None
        assert violation.reason is reason
        assert violation.player_id == 42


class TestActiveProfileSessionOwnership:
    @pytest.fixture
    def probe(self):
        rows = [
            [f"Player {index}", f"player-{index}", "AAA", "C"] + [None] * 27
            for index in range(4)
        ]
        index_html = (
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps({"props": {"pageProps": {"playersArray": rows}}})
            + "</script>"
        )
        body = (
            Path(__file__)
            .parent.joinpath("fixtures", "ingestion", "capwages_contract.html")
            .read_text()
        )
        return ActiveSessionProbe(
            index_html=index_html, profile_html=body, barrier=Barrier(4)
        )

    @pytest.fixture
    def service(self, probe):
        return ActiveContractService(
            session_factory=probe.open_session,
            repository_factory=open_active_repository,
        )

    @pytest.fixture
    def options(self):
        return ActiveContractOptions(minimum_players=4, workers=4)

    def test_owned_active_profiles_are_concurrent_and_closed(
        self, probe, service, options
    ):
        snapshot = service.fetch_snapshot(options)

        assert len(snapshot.profiles) == 4
        assert all(len(profile.contracts) == 1 for profile in snapshot.profiles)
        assert snapshot.failed_slugs == ()
        assert len({id(session) for session in probe.opened}) == 5
        assert {id(session) for session in probe.opened} == {
            id(session) for session in probe.closed
        }


class TestActiveContractOptionValidation:
    @pytest.fixture(
        params=[
            pytest.param({"minimum_players": 0}, id="no-players"),
            pytest.param({"minimum_profile_success_ratio": -0.1}, id="negative-ratio"),
            pytest.param({"minimum_profile_success_ratio": 1.1}, id="excess-ratio"),
            pytest.param(
                {"minimum_profile_success_ratio": float("nan")}, id="nan-ratio"
            ),
        ]
    )
    def invalid_options(self, request, monkeypatch):
        monkeypatch.setattr(ingestion, "track_active_contracts", reject_resource_access)
        return request.param

    def test_apply_rejects_before_tracking(self, invalid_options):
        with pytest.raises(ContractOptionError):
            ingestion.ingest_capwages(**invalid_options)


class TestProfileOptionsBeforeOwnership:
    @pytest.fixture(
        params=[
            pytest.param({"max_attempts": 0}, id="no-attempts"),
            pytest.param({"timeout": 0}, id="no-timeout"),
            pytest.param({"maximum_backoff": float("nan")}, id="nan-backoff"),
            pytest.param({"maximum_retry_after": -1}, id="negative-retry-after-limit"),
        ]
    )
    def scenario(self, request):
        probe = ProfileSessionProbe(
            response=SavedResponse(status_code=200, headers={}, text="", url=""),
            barrier=Barrier(1),
        )
        fetcher = ProfileFetcher(
            session_factory=probe.open_session,
            options=replace(ProfileHttpOptions(), **request.param),
        )
        candidate = Candidate(
            player_id=1,
            first_name="Pavel",
            last_name="Datsyuk",
            nhl_id="8467514",
            missing_seasons=(2008,),
        )
        return ProfileOptionScenario(probe=probe, fetcher=fetcher, candidate=candidate)

    def test_invalid_profile_options_open_no_session(self, scenario):
        probe, fetcher, candidate = scenario.probe, scenario.fetcher, scenario.candidate
        with pytest.raises(ContractOptionError):
            fetcher.fetch_profiles((candidate,), workers=1)
        assert probe.opened == []

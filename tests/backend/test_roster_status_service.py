"""Roster precedence, identity matching, and feed boundary regressions."""

from dataclasses import dataclass, field, replace
from datetime import date
from io import BytesIO
from urllib.request import Request

import pytest

from app.ScriptingFiles.FullDataScript.roster_status import http_json_client
from app.ScriptingFiles.FullDataScript.roster_status.ahl_roster_service import (
    AhlRosterService,
)
from app.ScriptingFiles.FullDataScript.roster_status.domain import (
    AhlFeedOptions,
    FetchResult,
    HttpOptions,
    RosterStatus,
)
from app.ScriptingFiles.FullDataScript.roster_status.errors import (
    InvalidJsonResponseError,
)
from app.ScriptingFiles.FullDataScript.roster_status.http_json_client import (
    JsonClient,
    JsonHttpClient,
    decode_json_or_jsonp,
)
from app.ScriptingFiles.FullDataScript.roster_status.nhl_roster_service import (
    NhlRosterService,
)
from app.ScriptingFiles.FullDataScript.roster_status.repository import RosterRepository
from app.ScriptingFiles.FullDataScript.roster_status.services import (
    RosterFeed,
    RosterStatusService,
)
from app.ScriptingFiles.FullDataScript.roster_status.tests.fakes import (
    FixedRosterFeed,
    MemoryHttpClient,
    MemoryRosterRepository,
)
from app.ScriptingFiles.FullDataScript.roster_status.util import (
    match_ahl_players,
    parse_birth_date,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class SyncScenario:
    service: RosterStatusService
    repository: MemoryRosterRepository
    expected: RosterStatus | None


class TestStatusPrecedence:
    @pytest.fixture(
        params=[
            pytest.param(
                (True, True, True, True, True, RosterStatus.LTIR), id="ltir-beats-both"
            ),
            pytest.param(
                (False, True, True, True, True, RosterStatus.ACTIVE), id="nhl-beats-ahl"
            ),
            pytest.param(
                (False, True, True, False, False, RosterStatus.ACTIVE),
                id="positive-nhl-on-partial-feeds",
            ),
            pytest.param(
                (False, False, True, True, True, RosterStatus.MINORS),
                id="ahl-identity-match",
            ),
            pytest.param(
                (False, False, True, True, False, RosterStatus.MINORS),
                id="positive-ahl-on-partial-ahl",
            ),
            pytest.param(
                (False, False, True, False, True, None),
                id="partial-nhl-preserves-status",
            ),
            pytest.param(
                (False, False, False, True, False, None),
                id="partial-ahl-preserves-status",
            ),
            pytest.param(
                (False, False, False, True, True, RosterStatus.UNKNOWN),
                id="complete-feeds-unknown",
            ),
        ]
    )
    def scenario(self, request, player, ahl_player):
        ltir, nhl_present, ahl_present, nhl_complete, ahl_complete, expected = (
            request.param
        )
        repository = MemoryRosterRepository(
            players=(player,),
            ltir_player_ids=frozenset({player.id}) if ltir else frozenset(),
        )
        nhl = FetchResult(
            items=(replace(ahl_player, external_id="11", full_name="Renamed Player"),)
            if nhl_present
            else (),
            errors=() if nhl_complete else ("NHL failed",),
        )
        ahl = FetchResult(
            items=(ahl_player,) if ahl_present else (),
            errors=() if ahl_complete else ("AHL failed",),
        )
        return SyncScenario(
            service=RosterStatusService(
                repository=repository,
                nhl_service=FixedRosterFeed(result=nhl),
                ahl_service=FixedRosterFeed(result=ahl),
            ),
            repository=repository,
            expected=expected,
        )

    def test_classification(self, scenario, caplog):
        summary = scenario.service.sync(date(2026, 9, 6))
        expected = {} if scenario.expected is None else {1: scenario.expected}
        assert scenario.repository.updates == expected
        assert summary.statuses_updated == len(expected)
        assert summary.preserved_count == (1 if scenario.expected is None else 0)
        assert sum(
            (
                summary.active_count,
                summary.minors_count,
                summary.ltir_count,
                summary.unknown_count,
            )
        ) == len(expected)
        assert caplog.records == []

    @pytest.fixture
    def missing_nhl_id(self, player):
        repository = MemoryRosterRepository(
            players=(replace(player, nhl_external_id=None),)
        )
        return RosterStatusService(
            repository=repository,
            nhl_service=FixedRosterFeed(),
            ahl_service=FixedRosterFeed(),
        ), repository

    def test_complete_feeds_do_not_guess_unknown_without_nhl_identity(
        self, missing_nhl_id
    ):
        service, repository = missing_nhl_id
        assert service.sync().preserved_count == 1
        assert repository.updates == {}

    @pytest.fixture
    def empty_collaborators(self):
        repository = MemoryRosterRepository()
        feed = FixedRosterFeed()
        return (
            RosterStatusService(
                repository=repository, nhl_service=feed, ahl_service=feed
            ),
            repository,
            feed,
        )

    def test_empty_valid_collaborators_are_retained(self, empty_collaborators):
        service, repository, feed = empty_collaborators
        assert isinstance(repository, RosterRepository)
        assert isinstance(feed, RosterFeed)
        assert service.repository is repository
        assert service.nhl_service is service.ahl_service is feed
        assert service.sync().statuses_updated == 0


class TestIdentityMatching:
    @pytest.fixture
    def known_id(self, player):
        return replace(
            player, ahl_external_id="7179", first_name="Old", last_name="Name"
        )

    def test_known_id_survives_name_and_birth_date_changes(self, known_id, ahl_player):
        assert match_ahl_players((known_id,), (ahl_player,)) == {
            known_id.id: ahl_player
        }

    def test_normalized_name_and_dob_map_conservatively(self, player, ahl_player):
        assert match_ahl_players((player,), (ahl_player,)) == {player.id: ahl_player}

    @pytest.fixture(
        params=[
            pytest.param("stored-identity", id="duplicate-stored-identity"),
            pytest.param("source-identity", id="duplicate-source-identity"),
            pytest.param("source-id", id="conflicting-source-id"),
            pytest.param("missing-birth-date", id="no-birth-date"),
            pytest.param("wrong-birth-date", id="wrong-birth-date"),
        ]
    )
    def ambiguous(self, request, player, ahl_player):
        players = (player,)
        feed = (ahl_player,)
        if request.param == "stored-identity":
            players += (replace(player, id=2),)
        if request.param == "source-identity":
            feed += (replace(ahl_player, external_id="99"),)
        if request.param == "source-id":
            feed += (replace(ahl_player, full_name="Different Person"),)
        if request.param == "missing-birth-date":
            feed = (replace(ahl_player, birth_date=None),)
        if request.param == "wrong-birth-date":
            feed = (replace(ahl_player, birth_date=date(1990, 1, 1)),)
        return players, feed

    def test_ambiguous_or_incomplete_identity_is_not_mapped(self, ambiguous):
        assert match_ahl_players(*ambiguous) == {}

    @pytest.fixture
    def claimed_identity(self, known_id, player, ahl_player):
        return (known_id, replace(player, id=2)), (ahl_player,)

    def test_known_external_id_cannot_be_claimed_again_by_name(self, claimed_identity):
        assert set(match_ahl_players(*claimed_identity)) == {1}


class TestFeedAdapters:
    @pytest.fixture
    def nhl(self, nhl_payloads):
        return NhlRosterService(http_client=MemoryHttpClient(responses=nhl_payloads))

    @pytest.fixture
    def ahl(self, ahl_payloads):
        client = MemoryHttpClient(responses=ahl_payloads)
        return AhlRosterService(http_client=client), client

    def test_nhl_players_and_immutable_result(self, nhl):
        result = nhl.fetch_current_rosters()
        assert result.complete
        assert isinstance(result.items, tuple)
        assert result.items[0].external_id == "11"
        assert result.items[0].full_name == "NHL Player"

    def test_ahl_identity_and_request_configuration(self, ahl):
        service, client = ahl
        assert isinstance(client, JsonClient)
        result = service.fetch_current_rosters()
        assert result.complete
        assert result.items[0].external_id == "7179"
        assert result.items[0].birth_date == date(1996, 8, 16)
        params = client.calls[1][1]
        assert params is not None
        assert params["season_id"] == "90"
        assert params["view"] == "roster"
        assert "rosterstatus" not in params

    @pytest.fixture
    def explicit_options(self, ahl_payloads, monkeypatch):
        monkeypatch.setenv("AHL_FEED_KEY", "ambient-key")
        monkeypatch.setenv("AHL_SEASON_ID", "ambient-season")
        client = MemoryHttpClient(responses=ahl_payloads)
        return AhlRosterService(
            http_client=client,
            options=AhlFeedOptions(feed_key="explicit-key", season_id="91"),
        ), client

    def test_options_and_empty_client_are_not_replaced(self, explicit_options):
        service, client = explicit_options
        assert len(client) == 0
        assert service.http_client is client
        service.fetch_current_rosters()
        assert client.calls[0][1]["key"] == "explicit-key"
        assert client.calls[1][1]["season_id"] == "91"

    @pytest.fixture(
        params=[
            pytest.param("nhl", id="nhl-partial"),
            pytest.param("ahl", id="ahl-partial"),
        ]
    )
    def partial(self, request, nhl_payloads, ahl_payloads):
        if request.param == "nhl":
            nhl_payloads["https://api-web.nhle.com/v1/roster/TOR/current"] = (
                TimeoutError("feed timeout")
            )
            return NhlRosterService(
                http_client=MemoryHttpClient(responses=nhl_payloads)
            )
        ahl_payloads["416"] = TimeoutError("feed timeout")
        return AhlRosterService(http_client=MemoryHttpClient(responses=ahl_payloads))

    def test_partial_feed_retains_positive_results_and_reports_once(
        self, partial, caplog
    ):
        result = partial.fetch_current_rosters()
        assert not result.complete
        assert len(result.items) == 1
        assert len(result.errors) == 1
        assert "timeout" in result.errors[0]
        assert caplog.records == []

    @pytest.fixture(
        params=[
            pytest.param(("nhl", "bootstrap", {}), id="nhl-malformed-standings"),
            pytest.param(
                ("nhl", "roster", {"forwards": "bad", "defensemen": [], "goalies": []}),
                id="nhl-malformed-roster",
            ),
            pytest.param(
                ("ahl", "bootstrap", {"teamsNoAll": "bad"}),
                id="ahl-malformed-bootstrap",
            ),
            pytest.param(
                ("ahl", "roster", {"roster": [{"sections": [{"data": [{}]}]}]}),
                id="ahl-malformed-player",
            ),
        ]
    )
    def malformed(self, request, nhl_payloads, ahl_payloads):
        feed, stage, payload = request.param
        if feed == "nhl":
            key = (
                "https://api-web.nhle.com/v1/standings/now"
                if stage == "bootstrap"
                else "https://api-web.nhle.com/v1/roster/EDM/current"
            )
            nhl_payloads[key] = payload
            return NhlRosterService(
                http_client=MemoryHttpClient(responses=nhl_payloads)
            )
        ahl_payloads["bootstrap" if stage == "bootstrap" else "415"] = payload
        return AhlRosterService(http_client=MemoryHttpClient(responses=ahl_payloads))

    def test_malformed_feed_is_incomplete(self, malformed):
        result = malformed.fetch_current_rosters()
        assert not result.complete
        assert len(result.errors) > 0

    @pytest.fixture
    def unexpected_failure(self, nhl_payloads):
        nhl_payloads["https://api-web.nhle.com/v1/standings/now"] = RuntimeError(
            "programming error"
        )
        return NhlRosterService(http_client=MemoryHttpClient(responses=nhl_payloads))

    def test_programming_errors_are_not_hidden_as_feed_absence(
        self, unexpected_failure
    ):
        with pytest.raises(RuntimeError, match="programming error"):
            unexpected_failure.fetch_current_rosters()


@dataclass(slots=True, kw_only=True, frozen=True)
class HttpOpener:
    response: BytesIO
    calls: list[tuple[Request, float]] = field(default_factory=list)

    def __call__(self, request: Request, *, timeout: float) -> BytesIO:
        self.calls.append((request, timeout))
        return self.response


class TestJsonTransport:
    @pytest.mark.parametrize(
        "body",
        [
            pytest.param('{"ok": true}', id="json"),
            pytest.param('JSON_CALLBACK({"ok": true});', id="jsonp"),
            pytest.param(
                ' jQuery.callback(\n{"ok": true}\n) ', id="qualified-callback"
            ),
        ],
    )
    def test_objects_decode(self, body):
        assert decode_json_or_jsonp(body) == {"ok": True}

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param("[]", id="array"),
            pytest.param("callback([])", id="wrapped-array"),
            pytest.param("({})", id="missing-callback-name"),
            pytest.param("callback({}) trailing", id="trailing-garbage"),
            pytest.param('callback({"broken":})', id="invalid-json"),
            pytest.param("callback({}", id="unterminated-callback"),
        ],
    )
    def test_invalid_envelopes_are_rejected(self, body):
        with pytest.raises(InvalidJsonResponseError):
            decode_json_or_jsonp(body)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            pytest.param(None, None, id="missing"),
            pytest.param("", None, id="empty"),
            pytest.param("invalid", None, id="malformed"),
            pytest.param("1996-08-16", date(1996, 8, 16), id="valid-date"),
        ],
    )
    def test_optional_birth_dates(self, value, expected):
        assert parse_birth_date(value) == expected

    @pytest.fixture
    def opener(self, monkeypatch):
        opener = HttpOpener(response=BytesIO(b'{"ok": true}'))
        monkeypatch.setattr(http_json_client, "urlopen", opener)
        return opener

    def test_timeout_headers_query_and_resource_closure(self, opener):
        result = JsonHttpClient(options=HttpOptions(timeout_seconds=2)).get_json(
            "https://feed.test", {"key": "a b"}
        )
        assert result == {"ok": True}
        request, timeout = opener.calls[0]
        assert timeout == 2
        assert request.full_url == "https://feed.test?key=a+b"
        assert request.get_header("User-agent") == "TradeValueRosterSync/1.0"
        assert opener.response.closed


class TestDuplicateAhlSightings:
    @pytest.fixture
    def repeated_identity(self, player, ahl_player):
        return replace(player, ahl_external_id=ahl_player.external_id), (
            ahl_player,
            replace(ahl_player, team_external_id="another-team"),
        )

    def test_identical_sightings_preserve_stable_id_matching(self, repeated_identity):
        player, sightings = repeated_identity
        assert match_ahl_players((player,), sightings)[player.id].external_id == "7179"

    @pytest.fixture
    def conflicting_feed(self, ahl_payloads):
        ahl_payloads["416"] = {
            "roster": [
                {
                    "sections": [
                        {
                            "data": [
                                {
                                    "row": {
                                        "player_id": "7179",
                                        "name": "Different Person",
                                        "birthdate": "1990-01-01",
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        return AhlRosterService(http_client=MemoryHttpClient(responses=ahl_payloads))

    def test_conflicting_profiles_make_the_feed_incomplete(self, conflicting_feed):
        result = conflicting_feed.fetch_current_rosters()
        assert not result.complete
        assert result.items == ()
        assert "conflicting profiles" in result.errors[0]


class TestEmptyFeedDiscovery:
    @pytest.fixture(
        params=[
            pytest.param(("nhl", {"standings": []}), id="no-nhl-teams"),
            pytest.param(
                ("ahl", {"current_season_id": "90", "teamsNoAll": []}),
                id="no-ahl-teams",
            ),
            pytest.param(("ahl", {"teamsNoAll": [{"id": "415"}]}), id="no-ahl-season"),
        ]
    )
    def feed(self, request):
        source, payload = request.param
        if source == "nhl":
            return NhlRosterService(
                http_client=MemoryHttpClient(
                    responses={"https://api-web.nhle.com/v1/standings/now": payload}
                )
            )
        return AhlRosterService(
            http_client=MemoryHttpClient(responses={"bootstrap": payload})
        )

    def test_empty_discovery_cannot_mark_existing_players_unknown(self, feed):
        result = feed.fetch_current_rosters()
        assert not result.complete
        assert len(result.errors) == 1
        assert result.items == ()


class TestIncompleteTeamDiscovery:
    @pytest.fixture
    def malformed_team_list(self, nhl_payloads):
        nhl_payloads["https://api-web.nhle.com/v1/standings/now"] = {
            "standings": [{"teamAbbrev": {"default": "EDM"}}, {"teamAbbrev": {}}]
        }
        return NhlRosterService(http_client=MemoryHttpClient(responses=nhl_payloads))

    def test_invalid_team_cannot_be_silently_dropped_from_discovery(
        self, malformed_team_list
    ):
        result = malformed_team_list.fetch_current_rosters()
        assert not result.complete
        assert result.items == ()

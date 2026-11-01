from app.ScriptingFiles.FullDataScript.contracts.tests.fixtures import (
    read_contract_fixture,
)
import json
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
from app.ScriptingFiles.FullDataScript.contracts.tests.fixtures import SavedResponse
from app.ScriptingFiles.FullDataScript.contracts.tests.transport import (
    CandidateCursor,
    ProfileScenario,
    ScriptedProfileSession,
    SleepRecorder,
)
import pytest
import requests
from app.ScriptingFiles.FullDataScript import capspace
from app.ScriptingFiles.FullDataScript.contracts import domain as contract_domain
from app.ScriptingFiles.FullDataScript.contracts import http as profile_http
from app.ScriptingFiles.FullDataScript.contracts import reporting as contract_reporting
from app.ScriptingFiles.FullDataScript.contracts import (
    repository as contract_repository,
)
from app.ScriptingFiles.FullDataScript.contracts.options import (
    HistoricalContractOptions,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas import documents
from app.ScriptingFiles.FullDataScript.contracts.tests.fakes import (
    EmptyContractRepository,
)
from app.ScriptingFiles.FullDataScript.contracts.tests.transport import (
    capwages_html,
    IdentityScenario,
    RequestScenario,
    TeamResolutionScenario,
    MetricsScenario,
    ParserCalls,
)

FIXTURES = Path(__file__).parent.joinpath("fixtures", "ingestion")


class TestDatsyukContractFixture:
    @pytest.fixture
    def datsyuk_html(self):
        return read_contract_fixture("capspace_datsyuk.html")

    def test_datsyuk_fixture_parses_identity_money_team_and_clause(self, datsyuk_html):
        contract = capspace.parse_capspace_page(
            datsyuk_html, expected_nhl_id="8467514"
        )[0]

        assert contract.external_id == "datsyuk-2007"
        assert contract.signed_on is not None
        assert contract.signed_on.isoformat() == "2007-04-06"
        assert contract.term_years == 7
        assert contract.total_value_cents == 4_690_000_000
        assert contract.signing_team == "Detroit Red Wings"
        assert contract.seasons[0].season_start_year == 2008
        assert contract.seasons[0].cap_hit_cents == 670_000_000
        assert contract.seasons[0].base_salary_cents == 670_000_000
        assert contract.seasons[0].signing_bonus_cents == 0
        assert contract.seasons[0].performance_bonus_cents == 0
        assert contract.seasons[0].clause == "NMC"


class TestEntryLevelContractFixture:
    @pytest.fixture
    def elc_html(self):
        return read_contract_fixture("capspace_elc.html")

    def test_elc_slide_is_explicit_and_does_not_fake_base_salary(self, elc_html):
        contract = capspace.parse_capspace_page(elc_html)[0]

        assert contract.is_entry_level is True
        slide = contract.seasons[0]
        assert slide.is_slide is True
        assert slide.base_salary_cents is None
        assert slide.minors_salary_cents == 9_500_000
        assert slide.cap_hit_cents == 95_000_000
        assert contract.seasons[1].performance_bonus_cents == 55_000_000
        assert contract.seasons[1].clause == "M-NTC"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("$6,700,000", 670_000_000, id="formatted-dollars"),
        pytest.param("0", 0, id="zero"),
        pytest.param("$1.25", 125, id="fractional-dollars"),
        pytest.param(None, None, id="missing"),
        pytest.param("", None, id="empty"),
    ],
)
def test_money_conversion_is_exact(value, expected):
    assert capspace.money_to_cents(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("garbage", id="malformed"),
        pytest.param("$-5", id="negative"),
        pytest.param("$NaN", id="nonfinite"),
    ],
)
def test_malformed_money_is_rejected(value):
    with pytest.raises(capspace.CapSpaceParseError):
        capspace.money_to_cents(value)


def test_changed_markup_and_malformed_season_are_not_silently_accepted():
    with pytest.raises(capspace.CapSpaceParseError):
        capspace.parse_capspace_page(
            "<html><body><h1>Changed markup</h1></body></html>"
        )
    with pytest.raises(capspace.CapSpaceParseError):
        capspace.season_start_year("not-a-season")


def test_page_with_no_contracts_is_distinct_from_malformed_markup():
    assert capspace.parse_capspace_page("<h1>Contract History</h1>") == ()


class TestProfileRequests:
    @pytest.fixture
    def candidate(self):
        return capspace.Candidate(
            player_id=7,
            first_name="Pavel",
            last_name="Datsyuk",
            nhl_id="8467514",
            missing_seasons=(2008, 2009),
        )

    @pytest.fixture
    def missing(self):
        return ScriptedProfileSession(
            responses=(SavedResponse(url="", status_code=404, headers={}, text=""),)
        )

    def test_nhl_id_is_the_only_url_identity(self, candidate, missing):
        outcome = profile_http.fetch_profile(missing, candidate)
        assert outcome.url == "https://cap-space.com/person/nhl:8467514"
        assert outcome.status == "not_found"

    @pytest.fixture
    def unidentified(self, candidate):
        return replace(candidate, nhl_id=None)

    @pytest.fixture
    def unused_session(self):
        return ScriptedProfileSession()

    def test_no_nhl_id_never_fetches_or_name_matches(
        self, unidentified, unused_session
    ):
        outcome = profile_http.fetch_profile(unused_session, unidentified)
        assert outcome.status == "no_nhl_id"
        assert unused_session.calls == []

    @pytest.fixture(
        params=[
            pytest.param("retry-after", id="retry-after-then-success"),
            pytest.param("timeout", id="timeout-exhaustion"),
            pytest.param("malformed-retry-after", id="exponential-fallback"),
            pytest.param(500, id="internal-error"),
            pytest.param(502, id="bad-gateway"),
            pytest.param(503, id="unavailable"),
            pytest.param(504, id="gateway-timeout"),
        ]
    )
    def retry(self, request, monkeypatch):
        responses = {
            "retry-after": (
                SavedResponse(
                    url="", status_code=429, headers={"Retry-After": "3"}, text=""
                ),
                SavedResponse(
                    url="",
                    status_code=200,
                    headers={},
                    text=read_contract_fixture("capspace_datsyuk.html"),
                ),
            ),
            "timeout": (requests.Timeout("slow"), requests.Timeout("slow")),
            "malformed-retry-after": (
                SavedResponse(
                    url="", status_code=429, headers={"Retry-After": "invalid"}, text=""
                ),
                SavedResponse(url="", status_code=404, headers={}, text=""),
            ),
        }
        expected = {
            "retry-after": ("succeeded", None, [3.0]),
            "timeout": ("failed", "timeout", [1.0]),
            "malformed-retry-after": ("not_found", None, [1.0]),
        }
        if isinstance(request.param, int):
            responses[request.param] = (
                SavedResponse(url="", status_code=request.param, headers={}, text=""),
            ) * 2
            expected[request.param] = ("failed", f"HTTP {request.param}", [1.0])
        status, error, delays = expected[request.param]
        scenario = ProfileScenario(
            session=ScriptedProfileSession(responses=responses[request.param]),
            sleep=SleepRecorder(),
            expected_status=contract_domain.ProfileStatus(status),
            expected_error=error,
            expected_delays=tuple(delays),
        )
        monkeypatch.setattr(profile_http.time, "sleep", scenario.sleep)
        return scenario

    def test_retry_status_backoff_and_request_bound(self, candidate, retry):
        outcome = profile_http.fetch_profile(retry.session, candidate, max_attempts=2)
        assert outcome.status == retry.expected_status
        assert outcome.error == retry.expected_error
        assert tuple(retry.sleep.delays) == retry.expected_delays
        assert len(retry.session.calls) == 2


class TestJsonContractPayloadIsSupported:
    @pytest.fixture
    def scenario(self):
        payload = {
            "props": {
                "pageProps": {
                    "person": {
                        "contracts": [
                            {
                                "id": "json-contract",
                                "type": "Standard Contract",
                                "value": "$1,000,000",
                                "term": 1,
                                "signingDate": "2020-07-01",
                                "signingTeam": "AAA",
                                "expiryStatus": "RFA",
                                "details": [
                                    {
                                        "season": "2020-21",
                                        "capHit": "$1,000,000",
                                        "nhlSalary": "$900,000",
                                    }
                                ],
                            }
                        ]
                    }
                }
            }
        }
        html = (
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload)
            + "</script>"
        )
        return html

    def test_json_contract_payload_is_supported(self, scenario):
        html = scenario
        contract = capspace.parse_capspace_page(html)[0]

        assert contract.external_id == "json-contract"
        assert contract.seasons[0].base_salary_cents == 90_000_000


class TestInvalidNextDataFallsBackToRenderedContractTable:
    @pytest.fixture
    def scenario(self):
        html = """
        <script id="__NEXT_DATA__" type="application/json">not-json</script>
        <article class="contract" data-contract-id="html-contract">
          <div>Total Value: $1,000,000 | Seasons: 1 | Signing Date: 2020-07-01</div>
          <table>
            <tr><td>Season</td><td>Cap Hit</td><td>NHL Salary</td></tr>
            <tr><td>2020-2021</td><td>$1,000,000</td><td>$1,000,000</td></tr>
          </table>
        </article>
        """
        return html

    def test_invalid_next_data_falls_back_to_rendered_contract_table(self, scenario):
        html = scenario
        contract = capspace.parse_capspace_page(html)[0]

        assert contract.external_id == "html-contract"
        assert contract.seasons[0].season_start_year == 2020


class TestJsonDatePluralBonusKeysAndIdentityAreSupported:
    @pytest.fixture
    def scenario(self):
        payload = {
            "props": {
                "pageProps": {
                    "player": {
                        "nhlId": 8470281,
                        "contracts": [
                            {
                                "type": "Standard Contract (Extension)",
                                "value": "$72,000,000",
                                "length": "13 years",
                                "signingDate": "Dec. 3, 2009",
                                "signingTeam": "Chicago Blackhawks",
                                "expiryStatus": "UFA",
                                "details": [
                                    {
                                        "season": "2010-11",
                                        "capHit": "$5,538,462",
                                        "baseSalary": "$5,000,000",
                                        "signingBonuses": "$3,000,000",
                                        "performanceBonuses": "$25,000",
                                    }
                                ],
                            }
                        ],
                    }
                }
            }
        }
        html = (
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload)
            + "</script>"
        )
        return html

    def test_json_date_plural_bonus_keys_and_identity_are_supported(self, scenario):
        html = scenario
        contract = capspace.parse_capspace_page(html, expected_nhl_id="8470281")[0]

        assert contract.signed_on is not None
        assert contract.signed_on.isoformat() == "2009-12-03"
        assert contract.seasons[0].signing_bonus_cents == 300_000_000
        assert contract.seasons[0].performance_bonus_cents == 2_500_000


class TestEmbeddedPageIdentityMustMatchTheCandidateNhlId:
    @pytest.fixture
    def scenario(self):
        payload = {"props": {"pageProps": {"player": {"nhlId": 1, "contracts": []}}}}
        html = (
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload)
            + "</script>"
        )
        return html

    def test_embedded_page_identity_must_match_the_candidate_nhl_id(self, scenario):
        html = scenario
        with pytest.raises(capspace.CapSpaceParseError, match="does not match"):
            capspace.parse_capspace_page(html, expected_nhl_id="2")


@pytest.fixture
def capwages_without_identity():
    return capwages_html(None)


def test_capwages_name_lookup_requires_an_embedded_nhl_id(capwages_without_identity):
    with pytest.raises(capspace.CapSpaceParseError, match="does not expose"):
        capspace.parse_capspace_page(
            capwages_without_identity,
            expected_nhl_id="8470000",
            require_nhl_id=True,
        )


class TestLegacyCapwagesIdentityRequiresNameSlugAndNhlStatsOverlap:
    @pytest.fixture
    def scenario(self):
        candidate = capspace.Candidate(
            player_id=7,
            first_name="Cory",
            last_name="Stillman",
            nhl_id="8458943",
            missing_seasons=(2010,),
        )
        payload = {
            "props": {
                "pageProps": {
                    "player": {
                        "name": "Stillman, Cory",
                        "slug": "cory-stillman",
                        "stats": [
                            {
                                "season": "2010-11",
                                "league": "NHL",
                                "gp": "65",
                            }
                        ],
                    }
                }
            }
        }
        html = (
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload)
            + "</script>"
        )
        return IdentityScenario(candidate=candidate, html=html)

    @pytest.fixture
    def outside_coverage(self, scenario):
        return replace(
            scenario.candidate, player_id=8, nhl_id="1", missing_seasons=(2011,)
        )

    def test_legacy_capwages_identity_requires_name_slug_and_nhl_stats_overlap(
        self, scenario, outside_coverage
    ):
        candidate = scenario.candidate
        html = scenario.html
        assert profile_http.matches_capwages_identity(
            html,
            candidate,
            "https://capwages.com/players/cory-stillman",
        )
        assert not profile_http.matches_capwages_identity(
            html,
            outside_coverage,
            "https://capwages.com/players/cory-stillman",
        )


class TestLegacyCapwagesIdentityRequiresPositiveNhlGames:
    cases = [
        pytest.param(
            '[{"season":"2010-11","league":"AHL","gp":"65"}]', id="minor-league"
        ),
        pytest.param('[{"season":"2010-11","league":"NHL","gp":"0"}]', id="zero-games"),
        pytest.param(
            '[{"season":"2010-11","league":"NHL","gp":"unknown"}]',
            id="unknown-games",
        ),
    ]

    @pytest.fixture(params=cases)
    def scenario(self, request):
        stats = json.loads(request.param)
        candidate = capspace.Candidate(
            player_id=7,
            first_name="Cory",
            last_name="Stillman",
            nhl_id="8458943",
            missing_seasons=(2010,),
        )
        payload = {
            "props": {
                "pageProps": {
                    "player": {
                        "name": "Stillman, Cory",
                        "slug": "cory-stillman",
                        "stats": stats,
                    }
                }
            }
        }
        html = (
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload)
            + "</script>"
        )
        return IdentityScenario(candidate=candidate, html=html)

    def test_legacy_capwages_identity_requires_positive_nhl_games(self, scenario):
        candidate = scenario.candidate
        html = scenario.html
        assert not profile_http.matches_capwages_identity(
            html,
            candidate,
            "https://capwages.com/players/cory-stillman",
        )


class TestCapwagesFallbackTriesDisambiguatedSlugAndPreservesSource:
    @pytest.fixture
    def scenario(self):
        candidate = capspace.Candidate(
            player_id=7,
            first_name="Colin",
            last_name="White",
            nhl_id="8470000",
            missing_seasons=(2010,),
        )
        session = ScriptedProfileSession(
            routes={
                "https://cap-space.com/person/nhl:8470000": SavedResponse(
                    status_code=200,
                    headers={},
                    text="<h1>Contract History</h1>",
                    url="",
                ),
                "https://capwages.com/players/colin-white": SavedResponse(
                    status_code=200, headers={}, text=capwages_html(1), url=""
                ),
                "https://capwages.com/players/colin-white-1": SavedResponse(
                    status_code=200, headers={}, text=capwages_html(8470000), url=""
                ),
            }
        )
        return RequestScenario(candidate=candidate, session=session)

    def test_capwages_fallback_tries_disambiguated_slug_and_preserves_source(
        self, scenario
    ):
        candidate = scenario.candidate
        session = scenario.session
        outcome = profile_http.fetch_profile_with_fallback(session, candidate)

        assert outcome.status == "succeeded"
        assert outcome.source_code == "capwages"
        assert outcome.fallback_attempted is True
        assert outcome.primary_status == "no_contracts"
        assert outcome.url.endswith("/colin-white-1")
        assert profile_http.covers_target_seasons(outcome) == {2010}


class TestMissingCapwagesBaseSlugDoesNotFanOutNumberedRequests:
    @pytest.fixture
    def scenario(self):
        candidate = capspace.Candidate(
            player_id=7,
            first_name="Absent",
            last_name="Player",
            nhl_id="8470000",
            missing_seasons=(2010,),
        )
        session = ScriptedProfileSession(
            responses=(SavedResponse(url="", status_code=404, headers={}, text=""),)
        )
        return RequestScenario(candidate=candidate, session=session)

    def test_missing_capwages_base_slug_does_not_fan_out_numbered_requests(
        self, scenario
    ):
        candidate = scenario.candidate
        session = scenario.session
        outcome = profile_http.fetch_capwages_profile(session, candidate)

        assert outcome.status == "not_found"
        assert session.calls == [("https://capwages.com/players/absent-player", 30)]


class TestCapwagesHostFailureStopsSlugFanout:
    @pytest.fixture
    def scenario(self):
        candidate = capspace.Candidate(
            player_id=7,
            first_name="Blocked",
            last_name="Player",
            nhl_id="8470000",
            missing_seasons=(2010,),
        )
        session = ScriptedProfileSession(
            responses=(SavedResponse(url="", status_code=403, headers={}, text=""),)
        )
        return RequestScenario(candidate=candidate, session=session)

    def test_capwages_host_failure_stops_slug_fanout(self, scenario):
        candidate = scenario.candidate
        session = scenario.session
        outcome = profile_http.fetch_capwages_profile(session, candidate)

        assert outcome.status == "failed"
        assert outcome.error == "HTTP 403"
        assert len(session.calls) == 1


class TestCapwagesSuccessParsesTheDocumentOnce:
    @pytest.fixture
    def scenario(self):
        candidate = capspace.Candidate(
            player_id=7,
            first_name="Fixture",
            last_name="Player",
            nhl_id="8470000",
            missing_seasons=(2010,),
        )
        session = ScriptedProfileSession(
            responses=(
                SavedResponse(
                    url="",
                    status_code=200,
                    headers={},
                    text=capwages_html(8470000),
                ),
            )
        )
        return RequestScenario(candidate=candidate, session=session)

    @pytest.fixture
    def parser_calls(self):
        with (
            patch.object(
                profile_http,
                "parse_source_document",
                wraps=profile_http.parse_source_document,
            ) as parse,
            patch.object(
                documents, "decode_page_payload", wraps=documents.decode_page_payload
            ) as decode,
        ):
            yield ParserCalls(parse=parse, decode=decode)

    def test_capwages_success_parses_the_document_once(self, scenario, parser_calls):
        outcome = profile_http.fetch_capwages_profile(
            scenario.session, scenario.candidate
        )
        assert outcome.status == capspace.STATUS_SUCCEEDED
        assert parser_calls.parse.call_count == 1
        assert parser_calls.decode.call_count == 1


class TestTeamResolutionPrefersSourceThenUniqueStint:
    @pytest.fixture
    def scenario(self):
        teams = {"det": 1, "detroit red wings": 1}
        stints = {2008: (2,), 2009: (2, 3)}
        return TeamResolutionScenario(teams=teams, stints=stints)

    def test_team_resolution_prefers_source_then_unique_stint(self, scenario):
        teams = scenario.teams
        stints = scenario.stints
        assert contract_repository.resolve_team_id(teams, stints, 2008, "DET") == 1
        assert contract_repository.resolve_team_id(teams, stints, 2008, None) == 2
        assert contract_repository.resolve_team_id(teams, stints, 2009, None) is None
        assert contract_repository.resolve_team_id(teams, stints, 2010, None) is None


class TestProfileMetricsAndSourceGroupingAreCentralized:
    @pytest.fixture
    def scenario(self):
        contract = capspace.parse_capspace_page(
            read_contract_fixture("capspace_datsyuk.html")
        )[0]
        covered = capspace.Candidate(
            player_id=7,
            first_name="Pavel",
            last_name="Datsyuk",
            nhl_id="8467514",
            missing_seasons=(2008,),
        )
        missing_id = capspace.Candidate(
            player_id=8,
            first_name="No",
            last_name="Identifier",
            nhl_id=None,
            missing_seasons=(2008,),
        )
        success = contract_domain.build_parsed_profile(
            candidate=covered,
            url="https://capwages.com/players/pavel-datsyuk",
            source_code=capspace.CAPWAGES_SOURCE,
            fallback_attempted=True,
            primary_status=capspace.STATUS_NO_CONTRACTS,
            fallback_status=capspace.STATUS_SUCCEEDED,
            contracts=(contract,),
        )
        failure = capspace.ProfileResult(
            candidate=covered,
            url="https://cap-space.com/person/nhl:8467514",
            fallback_attempted=True,
            fallback_status=capspace.STATUS_PARSE_FAILED,
            outcome=contract_domain.ProfileFailure(
                reason=contract_domain.FailureReason.FAILED, detail="fixture failure"
            ),
        )
        return MetricsScenario(
            covered=covered, missing_id=missing_id, success=success, failure=failure
        )

    def test_profile_metrics_and_source_grouping_are_centralized(self, scenario):
        covered = scenario.covered
        missing_id = scenario.missing_id
        success = scenario.success
        failure = scenario.failure
        metrics = contract_reporting.calculate_profile_metrics([success, failure])
        grouped = contract_reporting.group_source_records(
            [covered, missing_id], [success]
        )

        assert metrics["profiles_succeeded"] == 1
        assert metrics["profiles_with_target_coverage"] == 1
        assert metrics["profiles_failed"] == 1
        assert metrics["capwages_fallbacks_attempted"] == 2
        assert metrics["capwages_fallbacks_failed"] == 1
        assert grouped[capspace.CAPSPACE_SOURCE] == [
            (missing_id, {"status": capspace.STATUS_NO_NHL_ID})
        ]
        assert grouped[capspace.CAPWAGES_SOURCE][0][0] == covered
        assert (
            grouped[capspace.CAPWAGES_SOURCE][0][1]["status"]
            == capspace.STATUS_SUCCEEDED
        )


class TestNormalizeContractsPreservesTypedSeasonRows:
    @pytest.fixture
    def scenario(self):
        contract = capspace.parse_capspace_page(
            read_contract_fixture("capspace_datsyuk.html")
        )[0]
        return contract

    def test_normalize_contracts_preserves_typed_season_rows(self, scenario):
        contract = scenario
        normalized = capspace.normalize_contracts((contract,), "8467514")[0]

        assert normalized.external_id == "datsyuk-2007"
        assert normalized.seasons[0].season_start_year == 2008


class TestBuyoutRowsAreIgnoredAfterRealSalaryRows:
    @pytest.fixture
    def scenario(self):
        html = """
        <article class="contract">
          <div>Total Value: $8,000,000 | Seasons: 2 | Signing Date: 2018-07-01</div>
          <table>
            <tr><td>Season</td><td>Cap Hit</td><td>NHL Salary</td></tr>
            <tr><td>2018-2019</td><td>$4,000,000</td><td>$3,000,000</td></tr>
            <tr><td>2019-2020</td><td>$4,000,000</td><td>$3,000,000</td></tr>
            <tr><td>Buyout Years</td></tr>
            <tr><td>2020-2021</td><td>$2,000,000</td><td>$0</td></tr>
          </table>
        </article>
        """
        return html

    def test_buyout_rows_are_ignored_after_real_salary_rows(self, scenario):
        html = scenario
        contract = capspace.parse_capspace_page(html)[0]

        assert [row.season_start_year for row in contract.seasons] == [2018, 2019]


class TestNamedCapRecaptureSectionIsNotParsedAsContractSeasons:
    @pytest.fixture
    def scenario(self):
        html = """
        <article class="contract">
          <div>Total Value: $8,000,000 | Seasons: 2 | Signing Date: 2018-07-01</div>
          <table>
            <tr><td>Season</td><td>Cap Hit</td><td>NHL Salary</td></tr>
            <tr><td>2018-2019</td><td>$4,000,000</td><td>$3,000,000</td></tr>
            <tr><td>2019-2020</td><td>$4,000,000</td><td>$3,000,000</td></tr>
            <tr><td>Cap Recapture - Chicago Blackhawks</td></tr>
            <tr><td>Season</td><td>Cap Hit</td></tr>
            <tr><td>2019-2020</td><td>$4,000,000</td></tr>
            <tr><td>2020-2021</td><td>$2,000,000</td></tr>
          </table>
        </article>
        """
        return html

    def test_named_cap_recapture_section_is_not_parsed_as_contract_seasons(
        self, scenario
    ):
        html = scenario
        contract = capspace.parse_capspace_page(html)[0]

        assert [row.season_start_year for row in contract.seasons] == [2018, 2019]


def test_no_recorded_contracts_is_not_a_markup_failure():
    assert capspace.parse_capspace_page("<h1>No recorded contracts</h1>") == ()


class TestOneBadContractBlockDoesNotDiscardValidContractBlocks:
    @pytest.fixture
    def scenario(self):
        html = """
        <article class="contract">
          <div>Total Value: $1,000,000 | Seasons: 1</div>
          <table>
            <tr><td>Season</td><td>Cap Hit</td></tr>
            <tr><td>Buyout Years</td></tr>
          </table>
        </article>
        <article class="contract" data-contract-id="valid-contract">
          <div>Total Value: $2,000,000 | Seasons: 1 | Signing Date: 2020-07-01</div>
          <table>
            <tr><td>Season</td><td>Cap Hit</td><td>NHL Salary</td></tr>
            <tr><td>2020-2021</td><td>$2,000,000</td><td>$2,000,000</td></tr>
          </table>
        </article>
        """
        return html

    def test_one_bad_contract_block_does_not_discard_valid_contract_blocks(
        self, scenario
    ):
        html = scenario
        contracts = capspace.parse_capspace_page(html)

        assert len(contracts) == 1
        assert contracts[0].external_id == "valid-contract"


class TestCandidateQueryUsesBothStatTablesAndGapFilter:
    @pytest.fixture
    def scenario(self):
        cursor = CandidateCursor(
            rows=((1, "Pavel", "Datsyuk", "8467514", [2008, 2009]),)
        )
        return cursor

    def test_candidate_query_uses_both_stat_tables_and_gap_filter(self, scenario):
        cursor = scenario
        candidates = capspace.select_candidates(
            cursor, first_season=2008, last_season=2025
        )

        sql = cursor.statements[0][0]
        assert "skater_season_stats" in sql
        assert "goalie_season_stats" in sql
        assert "NOT EXISTS" in sql
        assert candidates[0].nhl_id == "8467514"
        assert cursor.statements[0][1] == [2008, 2025, 2008, 2025]


class TestCandidateQueryForceCanTargetACompletePlayerWithoutNameMatching:
    @pytest.fixture
    def scenario(self):
        cursor = CandidateCursor()
        return cursor

    def test_candidate_query_force_can_target_a_complete_player_without_name_matching(
        self, scenario
    ):
        cursor = scenario
        capspace.select_candidates(cursor, player_id=42, force=True)

        sql = cursor.statements[0][0]
        params = cursor.statements[0][1]
        assert "p.id = %s" in sql
        assert params is not None
        assert 42 in params
        assert "NOT EXISTS" not in sql


class TestTargetedPlayerStillSelectsOnlyMissingSeasonsWithoutForce:
    @pytest.fixture
    def scenario(self):
        cursor = CandidateCursor()
        return cursor

    def test_targeted_player_still_selects_only_missing_seasons_without_force(
        self, scenario
    ):
        cursor = scenario
        capspace.select_candidates(cursor, player_id=42)

        sql = cursor.statements[0][0]
        assert "p.id = %s" in sql
        assert "NOT EXISTS" in sql


@pytest.mark.parametrize(
    "options",
    [
        pytest.param((("workers", 0),), id="zero-workers"),
        pytest.param((("workers", capspace.MAX_WORKERS + 1),), id="excess-workers"),
        pytest.param((("batch_size", 0),), id="zero-batch"),
        pytest.param((("batch_size", capspace.MAX_BATCH_SIZE + 1),), id="excess-batch"),
    ],
    indirect=True,
)
def test_run_rejects_unsafe_worker_and_batch_bounds(options):
    with pytest.raises(ValueError):
        capspace.run_contract_sync(None, dry_run=True, **options)


@pytest.fixture
def options(request):
    return dict(request.param)


class TestRunReturnsCompleteEmptySummaryWithoutFetching:
    @pytest.fixture
    def scenario(self):
        repository = EmptyContractRepository()
        return repository

    @pytest.fixture
    def options(self):
        return HistoricalContractOptions()

    def test_run_returns_complete_empty_summary_without_fetching(
        self, scenario, options
    ):
        repository = scenario
        summary = capspace.run_historical_contracts(
            None,
            options=options,
            dry_run=True,
            repository_factory=repository.open_repository,
        )

        assert summary == {
            "candidate_player_seasons": 0,
            "candidate_players": 0,
            "players_without_nhl_ids": 0,
            "profiles_requested": 0,
            "records_read": 0,
            "records_created": 0,
            "records_updated": 0,
            "records_skipped": 0,
            "remaining_uncovered_player_seasons": 0,
        }

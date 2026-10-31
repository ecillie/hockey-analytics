"""Contract boundary regressions and generated amount/season inputs."""

from decimal import Decimal
import json
from pathlib import Path
from types import MappingProxyType

from hypothesis import given, strategies as st
import pytest

from app.ScriptingFiles.FullDataScript import capspace
from app.ScriptingFiles.FullDataScript.contracts.schemas.active import (
    parse_active_profile,
    parse_active_index,
)
from app.ScriptingFiles.FullDataScript.contracts.domain import (
    AbsenceReason,
    Candidate,
    ContractsAbsent,
    ContractsFound,
    ProfileFailure,
    ProfileStatus,
)
from app.ScriptingFiles.FullDataScript.contracts.errors import (
    ActiveContractError,
    CapSpaceParseError,
    ContractDocumentError,
    MoneyParseError,
    ProfileSlugError,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.contracts import (
    parse_capspace_page,
)
from app.ScriptingFiles.FullDataScript.contracts.tests.fixtures import (
    SavedResponse,
    SavedSession,
)
from app.ScriptingFiles.FullDataScript.contracts.util import (
    money_to_cents,
    season_start_year,
)


class TestAmountAndSeasonProperties:
    @given(
        amount=st.decimals(
            min_value=0,
            max_value=100_000_000,
            places=2,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    def test_currency_format_preserves_exact_cents(self, amount: Decimal) -> None:
        assert money_to_cents(f"${amount:,.2f}") == int(amount * 100)

    @given(
        amount=st.decimals(
            min_value=-100_000_000,
            max_value=Decimal("-0.01"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    def test_negative_amounts_never_become_zero(self, amount: Decimal) -> None:
        with pytest.raises(MoneyParseError):
            money_to_cents(amount)

    @given(year=st.integers(min_value=1900, max_value=2200))
    def test_short_and_full_seasons_agree_across_centuries(self, year: int) -> None:
        assert season_start_year(f"{year}-{(year + 1) % 100:02d}") == year
        assert season_start_year(f"{year}–{year + 1}") == year

    @pytest.fixture(
        params=(
            pytest.param("NaN", id="nan"),
            pytest.param("Infinity", id="infinity"),
            pytest.param("-Infinity", id="negative-infinity"),
            pytest.param("garbage", id="malformed"),
            pytest.param("1e999999", id="unrepresentable"),
        )
    )
    def invalid_amount(self, request: pytest.FixtureRequest) -> str:
        return request.param

    def test_invalid_money_is_a_structured_failure(self, invalid_amount: str) -> None:
        with pytest.raises(MoneyParseError) as failure:
            money_to_cents(invalid_amount)
        assert failure.value.value == invalid_amount

    @pytest.fixture(
        params=(
            pytest.param("2020-22", id="nonconsecutive-short"),
            pytest.param("2020-2022", id="nonconsecutive-full"),
            pytest.param("1899-1900", id="before-supported-range"),
            pytest.param("2201-2202", id="after-supported-range"),
        )
    )
    def invalid_season(self, request: pytest.FixtureRequest) -> str:
        return request.param

    def test_invalid_seasons_are_rejected(self, invalid_season: str) -> None:
        with pytest.raises(CapSpaceParseError):
            season_start_year(invalid_season)


class TestContractSourceShapes:
    @pytest.fixture(
        params=(
            pytest.param({"props": None}, id="null-props"),
            pytest.param(
                {"props": {"pageProps": {"player": []}}}, id="wrong-player-shape"
            ),
            pytest.param({"contracts": [{}]}, id="contract-without-seasons"),
            pytest.param(
                {"contracts": [{"details": [{"season": "2020-21", "capHit": "NaN"}]}]},
                id="invalid-cap-hit",
            ),
            pytest.param(
                {
                    "contracts": [
                        {
                            "value": "negative",
                            "details": [{"season": "2020-21", "capHit": "1"}],
                        }
                    ]
                },
                id="invalid-total-value",
            ),
            pytest.param(
                {
                    "contracts": [
                        {
                            "details": [
                                {"season": "2020-21", "capHit": "1"},
                                {"season": "2021-22", "capHit": "-2"},
                            ]
                        }
                    ]
                },
                id="partially-malformed-contract",
            ),
        )
    )
    def malformed_html(self, request: pytest.FixtureRequest) -> str:
        raw = request.param
        payload = raw if "props" in raw else {"props": {"pageProps": {"player": raw}}}
        return (
            '<h1>Contract History</h1><script type="application/json" id="__NEXT_DATA__">'
            + json.dumps(payload)
            + "</script>"
        )

    def test_malformed_profiles_are_not_reported_as_absence(
        self, malformed_html: str
    ) -> None:
        with pytest.raises(CapSpaceParseError):
            parse_capspace_page(malformed_html)

    @pytest.fixture
    def empty_profile(self) -> str:
        return '<script id="__NEXT_DATA__">{"props":{"pageProps":{"player":{"nhlId":123,"contracts":[]}}}}</script>'

    def test_explicit_empty_json_profile_is_legitimate_absence(
        self, empty_profile: str
    ) -> None:
        assert parse_capspace_page(empty_profile, expected_nhl_id="123") == ()
        assert parse_active_profile(empty_profile, slug="fixture") == ()

    @pytest.fixture
    def malformed_table(self) -> str:
        return "<h1>Contract History</h1><article><div>Total Value: $-1 | Seasons: 1</div><table><tr><td>Season</td><td>Cap Hit</td></tr><tr><td>2020-21</td><td>$1</td></tr></table></article>"

    def test_invalid_table_metadata_cannot_be_silently_dropped(
        self, malformed_table: str
    ) -> None:
        with pytest.raises(MoneyParseError):
            parse_capspace_page(malformed_table)

    @pytest.fixture
    def half_cent_profile(self) -> str:
        return '<script id="__NEXT_DATA__">{"props":{"pageProps":{"player":{"slug":"fixture","contracts":[{"value":"0.005","details":[{"season":"2020-21","capHit":"0.005"}]}]}}}}</script>'

    def test_each_source_retains_its_existing_rounding(
        self, half_cent_profile: str
    ) -> None:
        historical = parse_capspace_page(half_cent_profile)[0]
        active = parse_active_profile(half_cent_profile, slug="fixture")[0]
        assert historical.total_value_cents == historical.seasons[0].cap_hit_cents == 1
        assert active.total_value_cents == active.seasons[0].cap_hit_cents == 0

    @pytest.fixture
    def nullable_alias_profile(self) -> str:
        payload = {
            "props": {
                "pageProps": {
                    "player": {"nhlId": 123},
                    "person": {
                        "contracts": [
                            {
                                "type": None,
                                "contractType": "ELC",
                                "value": 0,
                                "totalValue": 500,
                                "term": None,
                                "termYears": 1,
                                "signingDate": None,
                                "signed_on": "2020-07-01",
                                "details": None,
                                "seasons": [{"season": "2020-21", "capHit": "$1"}],
                            }
                        ]
                    },
                }
            }
        }
        return '<script id="__NEXT_DATA__">' + json.dumps(payload) + "</script>"

    def test_nullable_aliases_preserve_zero_and_person_contracts(
        self, nullable_alias_profile: str
    ) -> None:
        contract = parse_capspace_page(nullable_alias_profile, expected_nhl_id="123")[0]
        assert contract.total_value_cents == 0
        assert contract.term_years == 1
        assert contract.contract_type == "ELC"
        assert contract.signed_on is not None
        assert contract.signed_on.isoformat() == "2020-07-01"

    def test_active_profile_rejects_a_different_slug(
        self, half_cent_profile: str
    ) -> None:
        with pytest.raises(ProfileSlugError):
            parse_active_profile(half_cent_profile, slug="someone-else")

    def test_active_profile_rejects_malformed_contracts(
        self, malformed_html: str
    ) -> None:
        with pytest.raises((ActiveContractError, ContractDocumentError)):
            parse_active_profile(malformed_html, slug="fixture")

    def test_active_index_requires_an_explicit_index(self, empty_profile: str) -> None:
        with pytest.raises(ContractDocumentError):
            parse_active_index(empty_profile, minimum_rows=0)


class TestProfileOutcomes:
    @pytest.fixture
    def candidate(self) -> Candidate:
        return Candidate(
            player_id=7,
            first_name="Pavel",
            last_name="Datsyuk",
            nhl_id="8467514",
            missing_seasons=(2008,),
        )

    @pytest.fixture(
        params=(
            pytest.param("84675140", id="id-prefix-redirect"),
            pytest.param("123", id="different-player-redirect"),
        )
    )
    def redirected_session(self, request: pytest.FixtureRequest) -> SavedSession:
        source = Path(__file__).parent.joinpath(
            "fixtures", "ingestion", "capspace_datsyuk.html"
        )
        return SavedSession(
            response=SavedResponse(
                status_code=200,
                headers=MappingProxyType({}),
                text=source.read_text(encoding="utf-8"),
                url=f"https://cap-space.com/person/nhl:{request.param}",
            )
        )

    def test_redirected_identity_is_a_failure(
        self, candidate: Candidate, redirected_session: SavedSession
    ) -> None:
        result = capspace._fetch_profile(redirected_session, candidate)
        assert isinstance(result.outcome, ProfileFailure)
        assert result.status is ProfileStatus.PARSE_FAILED
        assert result.contracts == ()

    @pytest.fixture(
        params=(
            pytest.param("<h1>Contract History</h1>", id="explicit-absence"),
            pytest.param("<h1>Unknown markup</h1>", id="unrecognized-markup"),
        )
    )
    def session(self, request: pytest.FixtureRequest) -> SavedSession:
        return SavedSession(
            response=SavedResponse(
                status_code=200,
                headers=MappingProxyType({}),
                text=request.param,
                url="https://cap-space.com/person/nhl:8467514",
            )
        )

    def test_absence_and_failure_are_distinct(
        self, candidate: Candidate, session: SavedSession
    ) -> None:
        result = capspace._fetch_profile(session, candidate)
        assert not isinstance(result.outcome, ContractsFound)
        if isinstance(result.outcome, ContractsAbsent):
            assert result.outcome.reason is AbsenceReason.NO_CONTRACTS
            assert result.error is None
            return
        assert isinstance(result.outcome, ProfileFailure)
        assert result.error is not None

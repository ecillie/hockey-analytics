"""Contract source snapshot isolation and serialized compatibility."""

from pathlib import Path

import pytest

from app.ScriptingFiles.FullDataScript.capspace import parse_capspace_page
from app.ScriptingFiles.FullDataScript.contracts.schemas.serialization import (
    serialize_contract,
)
from app.ScriptingFiles.FullDataScript.contracts.domain import (
    ParsedContract,
)


class TestContractSnapshots:
    @pytest.fixture
    def contract(self) -> ParsedContract:
        source = Path(__file__).parent.joinpath(
            "fixtures", "ingestion", "capspace_datsyuk.html"
        )
        return parse_capspace_page(source.read_text(encoding="utf-8"))[0]

    def test_contract_snapshot_is_not_mutated_by_consumers(
        self, contract: ParsedContract
    ) -> None:
        payload = contract.source_payload
        assert payload is not None
        payload.clear()
        assert contract.source_payload is not None
        assert len(contract.source_payload) > 0

    def test_season_snapshot_is_not_mutated_by_consumers(
        self, contract: ParsedContract
    ) -> None:
        season = contract.seasons[0]
        payload = season.source_payload
        assert payload is not None
        payload.clear()
        assert season.source_payload is not None
        assert len(season.source_payload) > 0

    def test_serialization_preserves_the_source_record_shape(
        self, contract: ParsedContract
    ) -> None:
        payload = serialize_contract(contract)
        assert "source_snapshot" not in payload
        assert payload["source_payload"] == contract.source_payload
        seasons = payload["seasons"]
        assert isinstance(seasons, tuple)
        assert seasons[0]["cap_hit_cents"] == 670_000_000
        assert seasons[0]["source_payload"] == contract.seasons[0].source_payload
        assert "source_snapshot" not in seasons[0]


class TestCapWagesSnapshots:
    @pytest.fixture
    def contract(self) -> ParsedContract:
        source = Path(__file__).parent.joinpath(
            "fixtures", "ingestion", "capwages_contract.html"
        )
        return parse_capspace_page(
            source.read_text(encoding="utf-8"), expected_nhl_id="123"
        )[0]

    def test_nested_snapshot_changes_cannot_modify_the_contract(
        self, contract: ParsedContract
    ) -> None:
        snapshot = contract.source_payload
        assert snapshot is not None
        details = snapshot["details"]
        assert isinstance(details, list)
        details[0]["capHit"] = "0"
        assert contract.source_payload != snapshot
        assert contract.seasons[0].cap_hit_cents == 100_000_000

    def test_owning_teams_and_clauses_survive_normalization(
        self, contract: ParsedContract
    ) -> None:
        assert contract.signing_team == "AAA"
        assert tuple(season.owning_team for season in contract.seasons) == (
            "BBB",
            "CCC",
        )
        assert tuple(season.clause for season in contract.seasons) == ("NMC", "M-NTC")
        assert contract.is_entry_level
        assert contract.seasons[1].is_slide
        assert contract.seasons[1].base_salary_cents is None

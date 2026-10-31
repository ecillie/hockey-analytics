"""Canonical source identities, deduplication, and independent quality invariants."""

import pytest
from hypothesis import given

from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    DataQualityReport,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.errors import (
    DuplicateRatioViolation,
    RowCountViolation,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.services import (
    normalize_row,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.services import (
    normalize_stat_row,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.policy import (
    find_quality_violation,
    validate_rows,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.tests.identities import (
    IdentityRows,
    equivalent_identity_rows,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.util import source_row_hash


@given(equivalent_identity_rows())
def test_equivalent_player_ids_normalize_without_changing_source_snapshots(
    scenario: IdentityRows,
):
    for case in scenario.kinds:
        puck_rows = tuple(
            normalize_row(raw, case.job.kind, case.advanced)
            for raw in scenario.moneypuck
        )
        nhl_rows = tuple(
            normalize_stat_row(
                raw,
                case.job,
                case.basic,
            )
            for raw in scenario.nhl
        )
        assert {row.external_id for row in puck_rows + nhl_rows} == {
            str(scenario.player_id)
        }
        assert (
            tuple(row.source_row_hash for row in puck_rows) == scenario.moneypuck_hashes
        )
        assert tuple(row.source_row_hash for row in nhl_rows) == scenario.nhl_hashes
    assert tuple(map(source_row_hash, scenario.moneypuck)) == scenario.moneypuck_hashes
    assert tuple(map(source_row_hash, scenario.nhl)) == scenario.nhl_hashes
    assert len(set(scenario.moneypuck_hashes)) == len(scenario.moneypuck)


@given(equivalent_identity_rows())
def test_integer_grain_deduplicates_aliases_with_last_original_snapshot_winning(
    scenario: IdentityRows,
):
    rows, report = validate_rows(scenario.moneypuck, scenario.policy)
    assert rows == (scenario.moneypuck[-1],)
    assert report.records_read == 5
    assert report.records_valid == 1
    assert report.duplicate_records == 4
    assert report.seasons == (2025,)
    assert source_row_hash(rows[0]) == scenario.moneypuck_hashes[-1]


class TestQualityPolicyPrecedence:
    @pytest.fixture(
        params=[
            pytest.param((1, 9, 2, 0.0, RowCountViolation), id="count-before-ratio"),
            pytest.param(
                (1, 9, 1, 0.0, DuplicateRatioViolation), id="ratio-after-count"
            ),
            pytest.param((1, 9, 1, 0.9, None), id="exact-count-and-ratio-boundary"),
            pytest.param((0, 0, 0, 0.0, None), id="empty-report"),
            pytest.param((0, 10, 0, 1.0, None), id="maximum-ratio-boundary"),
        ]
    )
    def scenario(self, request):
        valid, duplicates, minimum, maximum, error = request.param
        return (
            DataQualityReport(
                source="fixture",
                records_read=valid + duplicates,
                records_valid=valid,
                duplicate_records=duplicates,
                seasons=(),
            ),
            minimum,
            maximum,
            error,
        )

    def test_count_and_ratio_keep_failure_precedence_and_context(self, scenario):
        report, minimum, maximum, error = scenario
        violation = find_quality_violation(
            report, minimum_rows=minimum, maximum_duplicate_ratio=maximum
        )
        if error is None:
            assert violation is None
            return
        assert violation is not None
        assert isinstance(violation, error)
        assert violation.source == report.source
        if isinstance(violation, RowCountViolation):
            assert violation.actual == report.records_valid
            assert violation.minimum == minimum
        if isinstance(violation, DuplicateRatioViolation):
            assert violation.actual == report.duplicate_ratio
            assert violation.maximum == maximum

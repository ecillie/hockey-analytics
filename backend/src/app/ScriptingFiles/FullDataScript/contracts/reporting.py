"""Contract profile snapshots and source-attributed run metrics."""

from collections import Counter
from collections.abc import Iterable

from app.ScriptingFiles.FullDataScript.contracts.domain import (
    Candidate,
    ProfileResult,
    ProfileSource,
    ProfileStatus,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.serialization import (
    serialize_contract,
)


def result_source_payload(result: ProfileResult) -> dict[str, object]:
    return {
        "status": result.status,
        "error": result.error,
        "url": result.url,
        "contracts": [serialize_contract(contract) for contract in result.contracts],
    }


def source_records_by_code(
    candidates: Iterable[Candidate],
    results: Iterable[ProfileResult],
) -> dict[str, list[tuple[Candidate, dict[str, object]]]]:
    grouped: dict[str, list[tuple[Candidate, dict[str, object]]]] = {
        ProfileSource.CAPSPACE: [
            (candidate, {"status": ProfileStatus.NO_NHL_ID})
            for candidate in candidates
            if candidate.nhl_id in (None, "")
        ]
    }
    for result in results:
        grouped.setdefault(result.source_code, []).append(
            (result.candidate, result_source_payload(result))
        )
    return grouped


def profile_metrics(results: Iterable[ProfileResult]) -> Counter[str]:
    materialized = list(results)
    return Counter(
        {
            "profiles_succeeded": sum(
                result.status == ProfileStatus.SUCCEEDED for result in materialized
            ),
            "profiles_with_target_coverage": sum(
                result.covers_target for result in materialized
            ),
            "profiles_not_found": sum(
                result.status == ProfileStatus.NOT_FOUND for result in materialized
            ),
            "profiles_failed": sum(
                result.status in (ProfileStatus.FAILED, ProfileStatus.PARSE_FAILED)
                for result in materialized
            ),
            "profiles_no_contracts": sum(
                result.status == ProfileStatus.NO_CONTRACTS for result in materialized
            ),
            "profiles_no_matching_contracts": sum(
                result.status == ProfileStatus.NO_MATCHING_CONTRACTS
                for result in materialized
            ),
            "capspace_profiles_succeeded": sum(
                result.status == ProfileStatus.SUCCEEDED
                and result.source_code == ProfileSource.CAPSPACE
                for result in materialized
            ),
            "capwages_profiles_succeeded": sum(
                result.status == ProfileStatus.SUCCEEDED
                and result.source_code == ProfileSource.CAPWAGES
                for result in materialized
            ),
            "capwages_fallbacks_attempted": sum(
                result.fallback_attempted for result in materialized
            ),
            "capwages_fallbacks_failed": sum(
                result.fallback_status
                in (ProfileStatus.FAILED, ProfileStatus.PARSE_FAILED)
                for result in materialized
            ),
            "capwages_fallbacks_not_found": sum(
                result.fallback_status == ProfileStatus.NOT_FOUND
                for result in materialized
            ),
            "contracts_parsed": sum(len(result.contracts) for result in materialized),
        }
    )


def unprocessed_count(summary: dict[str, int]) -> int:
    return (
        summary.get("records_skipped", 0)
        + summary.get("players_without_nhl_ids", 0)
        + summary.get("profiles_failed", 0)
        + summary.get("profiles_not_found", 0)
    )

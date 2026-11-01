"""Bounded profile fetching and independently committed contract batches."""

from collections import Counter
from collections.abc import Generator, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field

from app.ScriptingFiles.FullDataScript.contracts.domain import Candidate, ProfileResult
from app.ScriptingFiles.FullDataScript.contracts.http import (
    ProfileSessionFactory,
    fetch_profile_with_fallback,
)
from app.ScriptingFiles.FullDataScript.contracts.options import (
    ContractOptionError,
    HistoricalContractOptions,
    ProfileHttpOptions,
    find_option_violation,
    find_profile_http_violation,
)
from app.ScriptingFiles.FullDataScript.contracts.reporting import (
    calculate_profile_metrics,
    count_unprocessed_records,
)
from app.ScriptingFiles.FullDataScript.contracts.repository import (
    ContractRepositoryFactory,
)
from app.ScriptingFiles.FullDataScript.tracking.errors import IngestionBatchError


@dataclass(slots=True, kw_only=True, frozen=True)
class ProfileFetcher:
    session_factory: ProfileSessionFactory
    options: ProfileHttpOptions = field(default_factory=ProfileHttpOptions)

    def fetch_candidate(self, candidate: Candidate) -> ProfileResult:
        if violation := find_profile_http_violation(self.options):
            raise violation
        with self.session_factory() as session:
            return fetch_profile_with_fallback(session, candidate, options=self.options)

    def fetch_profiles(
        self, candidates: tuple[Candidate, ...], workers: int
    ) -> tuple[ProfileResult, ...]:
        if not 1 <= workers <= 8:
            raise ContractOptionError(
                option="workers", requirement="must be between 1 and 8"
            )
        if violation := find_profile_http_violation(self.options):
            raise violation
        with ThreadPoolExecutor(
            max_workers=min(workers, max(1, len(candidates)))
        ) as executor:
            futures = tuple(
                executor.submit(self.fetch_candidate, candidate)
                for candidate in candidates
                if candidate.nhl_id not in (None, "")
            )
            return tuple(future.result() for future in as_completed(futures))


def summarize_progress(summary: dict[str, int], *, dry_run: bool) -> dict[str, int]:
    result = dict(summary)
    result["records_read"] = summary.get("processed_player_seasons", 0)
    result["records_created"] = 0
    result["records_updated"] = 0
    if dry_run:
        result["proposed_contracts"] = summary.get("contracts_parsed", 0)
        result["records_skipped"] = count_unprocessed_records(summary)
        return result
    result["records_read"] += summary.get("contracts_parsed", 0)
    result["records_created"] = summary.get("contracts_created", 0) + summary.get(
        "contract_seasons_created", 0
    )
    result["records_updated"] = summary.get("contracts_matched", 0) + summary.get(
        "contract_seasons_updated", 0
    )
    result["records_skipped"] = count_unprocessed_records(summary)
    return result


@contextmanager
def report_batch_failure(
    stage: str, committed: Mapping[str, int], *, dry_run: bool
) -> Generator[None]:
    try:
        yield
    except Exception as failure:
        progress = summarize_progress(dict(committed), dry_run=dry_run)
        raise IngestionBatchError(
            stage=stage, committed_summary=progress, failure=failure
        ) from failure


@dataclass(slots=True, kw_only=True, frozen=True)
class HistoricalContractService:
    repository_factory: ContractRepositoryFactory
    fetcher: ProfileFetcher

    def run(
        self, options: HistoricalContractOptions, *, dry_run: bool
    ) -> dict[str, int]:
        if violation := find_option_violation(options):
            raise violation
        with self.repository_factory() as repository:
            candidates = repository.select_candidates(options)
        summary = {
            "candidate_player_seasons": sum(
                len(item.missing_seasons) for item in candidates
            ),
            "candidate_players": len(candidates),
            "players_without_nhl_ids": sum(
                item.nhl_id in (None, "") for item in candidates
            ),
            "profiles_requested": sum(
                item.nhl_id not in (None, "") for item in candidates
            ),
        }
        if len(candidates) == 0:
            summary.update(
                records_read=0,
                records_created=0,
                records_updated=0,
                records_skipped=0,
                remaining_uncovered_player_seasons=0,
            )
            return summary
        committed: Counter[str] = Counter()
        for offset in range(0, len(candidates), options.batch_size):
            batch = candidates[offset : offset + options.batch_size]
            with report_batch_failure("fetch", committed, dry_run=dry_run):
                results = self.fetcher.fetch_profiles(batch, options.workers)
            with report_batch_failure("persist", committed, dry_run=dry_run):
                with self.repository_factory() as repository:
                    batch_summary = repository.persist_batch(
                        batch, results, options, dry_run=dry_run
                    )
            committed.update(batch_summary)
            committed.update(calculate_profile_metrics(results))
            committed["processed_player_seasons"] += sum(
                len(item.missing_seasons) for item in batch
            )
            committed["players_without_nhl_ids"] += sum(
                item.nhl_id in (None, "") for item in batch
            )
            committed["batches_processed"] += 1
            committed["profiles_requested"] += len(results)
        summary.update(committed)
        summary = summarize_progress(summary, dry_run=dry_run)
        if not dry_run:
            with report_batch_failure("coverage", committed, dry_run=dry_run):
                with self.repository_factory() as repository:
                    coverage = repository.coverage_counts(options)
                missing = coverage["missing_player_seasons"]
                assert isinstance(missing, int)
                summary["remaining_uncovered_player_seasons"] = missing
        return summary

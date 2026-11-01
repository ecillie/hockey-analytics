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
    HistoricalContractOptions,
    HistoricalContractLimits,
    ProfileHttpOptions,
    find_option_violation,
    find_profile_http_violation,
)
from app.ScriptingFiles.FullDataScript.contracts.policy import WorkerLimitPolicy
from app.ScriptingFiles.FullDataScript.contracts.reporting import (
    calculate_profile_metrics,
    count_unprocessed_records,
)
from app.ScriptingFiles.FullDataScript.contracts.repository import (
    ContractRepositoryFactory,
)
from app.ScriptingFiles.FullDataScript.tracking.errors import IngestionBatchError
from app.ScriptingFiles.FullDataScript.tracking.domain import IngestionContext
from app.ScriptingFiles.FullDataScript.tracking.services import (
    report_ingestion_progress,
)
from app.ScriptingFiles.FullDataScript.tracking.util import collect_ingestion_counts
from app.shared.observability.domain import LogLevel


@dataclass(slots=True, kw_only=True, frozen=True)
class ProfileFetcher:
    session_factory: ProfileSessionFactory
    options: ProfileHttpOptions = field(default_factory=ProfileHttpOptions)
    context: IngestionContext | None = None

    def fetch_candidate(self, candidate: Candidate) -> ProfileResult:
        if violation := find_profile_http_violation(self.options):
            raise violation
        with self.session_factory() as session:
            return fetch_profile_with_fallback(
                session, candidate, options=self.options, context=self.context
            )

    def fetch_profiles(
        self,
        candidates: tuple[Candidate, ...],
        workers: int,
        *,
        limits: HistoricalContractLimits | None = None,
    ) -> tuple[ProfileResult, ...]:
        limits = HistoricalContractLimits() if limits is None else limits
        if violation := WorkerLimitPolicy(
            maximum_workers=limits.maximum_workers
        ).find_violation(workers):
            raise violation
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


def summarize_progress(summary: Mapping[str, int], *, dry_run: bool) -> dict[str, int]:
    result = dict(summary)
    result["records_read"] = summary.get("processed_player_seasons", 0)
    result["records_created"] = 0
    result["records_updated"] = 0
    if dry_run:
        result["proposed_contracts"] = summary.get("contracts_parsed", 0)
        result["records_skipped"] = count_unprocessed_records(result)
        return result
    result["records_read"] += summary.get("contracts_parsed", 0)
    result["records_created"] = summary.get("contracts_created", 0) + summary.get(
        "contract_seasons_created", 0
    )
    result["records_updated"] = summary.get("contracts_matched", 0) + summary.get(
        "contract_seasons_updated", 0
    )
    result["records_skipped"] = count_unprocessed_records(result)
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
    context: IngestionContext | None = None

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
            report_ingestion_progress(
                self.context,
                event="ingestion.batch_started",
                values={"attempted": len(batch)},
                level=LogLevel.DEBUG,
            )
            with report_batch_failure("fetch", committed, dry_run=dry_run):
                results = self.fetcher.fetch_profiles(
                    batch, options.workers, limits=options.limits
                )
            profile_metrics = calculate_profile_metrics(results)
            if profile_metrics["capwages_fallbacks_attempted"] > 0:
                report_ingestion_progress(
                    self.context,
                    event="ingestion.fallback_summary",
                    values={
                        "source": "capwages",
                        "attempted": profile_metrics["capwages_fallbacks_attempted"],
                        "failed": profile_metrics["capwages_fallbacks_failed"],
                    },
                    level=LogLevel.WARNING,
                )
            with report_batch_failure("persist", committed, dry_run=dry_run):
                with self.repository_factory() as repository:
                    batch_summary = repository.persist_batch(
                        batch, results, options, dry_run=dry_run
                    )
            committed.update(batch_summary)
            committed.update(profile_metrics)
            committed["processed_player_seasons"] += sum(
                len(item.missing_seasons) for item in batch
            )
            committed["players_without_nhl_ids"] += sum(
                item.nhl_id in (None, "") for item in batch
            )
            committed["batches_processed"] += 1
            committed["profiles_requested"] += len(results)
            report_ingestion_progress(
                self.context,
                event="ingestion.batch_previewed"
                if dry_run
                else "ingestion.batch_committed",
                values=(
                    {"fetched": len(results), "committed": 0}
                    if dry_run
                    else collect_ingestion_counts(
                        summarize_progress(batch_summary, dry_run=False)
                    )
                ),
            )
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

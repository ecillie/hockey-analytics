"""Validate a bounded active CapWages fetch before opening its write transaction."""

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from app.ScriptingFiles.FullDataScript.tracking.domain import IngestionContext
from app.ScriptingFiles.FullDataScript.tracking.services import (
    report_ingestion_progress,
)
from app.shared.observability.domain import LogLevel

import requests
from app.ScriptingFiles.FullDataScript.contracts.repository.active import (
    ActiveRepositoryFactory,
)
from app.ScriptingFiles.FullDataScript.contracts.domain import (
    ActiveContractProfile,
    ActiveContractSnapshot,
    ActivePlayer,
    ParsedContract,
)
from app.ScriptingFiles.FullDataScript.contracts.errors import (
    ActiveProfileCoverageError,
)
from app.ScriptingFiles.FullDataScript.contracts.repository.http import (
    ActiveSessionFactory,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.repository.http import (
    report_request_recovery,
)
from app.ScriptingFiles.FullDataScript.contracts.domain import ActiveContractOptions
from app.ScriptingFiles.FullDataScript.contracts.policy import (
    find_active_option_violation,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.active import (
    parse_active_index,
    parse_active_players,
    parse_active_profile,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class ActiveContractService:
    session_factory: ActiveSessionFactory
    repository_factory: ActiveRepositoryFactory
    context: IngestionContext | None = None

    def fetch_players(self, options: ActiveContractOptions) -> tuple[ActivePlayer, ...]:
        with self.session_factory() as session:
            response = session.get("https://capwages.com/players/active", timeout=60)
            response.raise_for_status()
            report_request_recovery(response, self.context)
            active = parse_active_index(
                response.text, minimum_rows=options.minimum_players
            )
            return tuple(
                parse_active_players(active, minimum_rows=options.minimum_players)
            )

    def fetch_contracts(self, player: ActivePlayer) -> tuple[ParsedContract, ...]:
        with self.session_factory() as session:
            response = session.get(
                f"https://capwages.com/players/{player.slug}", timeout=30
            )
            response.raise_for_status()
            report_request_recovery(response, self.context)
            return parse_active_profile(response.text, slug=player.slug)

    def fetch_snapshot(self, options: ActiveContractOptions) -> ActiveContractSnapshot:
        players = self.fetch_players(options)
        contracts: dict[str, tuple[ParsedContract, ...]] = {}
        failed: list[str] = []
        with ThreadPoolExecutor(max_workers=options.workers) as executor:
            futures = {
                executor.submit(self.fetch_contracts, player): player.slug
                for player in players
            }
            for future in as_completed(futures):
                slug = futures[future]
                completed = resolve_profile_future(future)
                if completed is None:
                    failed.append(slug)
                if completed is not None:
                    contracts[slug] = completed
        ratio = (len(players) - len(failed)) / len(players)
        if ratio < options.minimum_profile_success_ratio:
            raise ActiveProfileCoverageError(
                ratio=ratio, minimum=options.minimum_profile_success_ratio
            )
        report_ingestion_progress(
            self.context,
            event="ingestion.profiles_fetched",
            values={
                "fetched": len(players),
                "validated": len(contracts),
                "failed": len(failed),
            },
            level=LogLevel.DEBUG,
        )
        return ActiveContractSnapshot(
            profiles=tuple(
                ActiveContractProfile(
                    player=player, contracts=contracts.get(player.slug, ())
                )
                for player in players
            ),
            failed_slugs=tuple(failed),
        )

    def run(self, options: ActiveContractOptions) -> dict[str, int | str]:
        if violation := find_active_option_violation(options):
            raise violation
        snapshot = self.fetch_snapshot(options)
        report_ingestion_progress(
            self.context,
            event="ingestion.validated",
            values={"validated": len(snapshot.profiles)},
        )
        with self.repository_factory() as repository:
            return repository.save_snapshot(snapshot)


def resolve_profile_future(
    future: Future[tuple[ParsedContract, ...]],
) -> tuple[ParsedContract, ...] | None:
    try:
        return future.result()
    except requests.RequestException:
        return None

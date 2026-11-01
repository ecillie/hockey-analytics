"""Conservative CapWages identity matching for current and legacy pages."""

import re
from dataclasses import dataclass

from app.ScriptingFiles.FullDataScript.contracts.domain import (
    Candidate,
    ParsedContract,
    StoredContract,
)
from app.ScriptingFiles.FullDataScript.contracts.errors import (
    CapSpaceParseError,
    ContractConflictError,
    ReconciliationFailure,
    ContractOptionError,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas import SourceDocument
from app.ScriptingFiles.FullDataScript.contracts.schemas.documents import PageSnapshots
from app.ScriptingFiles.FullDataScript.contracts.schemas.contracts import (
    extract_embedded_nhl_id,
    extract_mapping_rows,
    extract_page_player,
)
from app.ScriptingFiles.FullDataScript.contracts.util import clean_text
from app.ScriptingFiles.FullDataScript.source_ingestion.util import build_player_slug


@dataclass(slots=True, kw_only=True, frozen=True)
class WorkerLimitPolicy:
    maximum_workers: int

    def find_violation(self, workers: int) -> ContractOptionError | None:
        if 1 <= workers <= self.maximum_workers:
            return None
        return ContractOptionError(
            option="workers",
            requirement=f"must be between 1 and {self.maximum_workers}",
        )


def matches_capwages_document(
    document: SourceDocument,
    candidate: Candidate,
    url: str,
    *,
    pages: PageSnapshots | None = None,
) -> bool:
    payloads = document.next_data if pages is None else pages
    try:
        identity = extract_embedded_nhl_id(payloads)
        player = next(
            (
                row
                for payload in payloads
                if len(row := extract_page_player(payload)) > 0
            ),
            {},
        )
    except CapSpaceParseError:
        return False
    if identity is not None:
        return candidate.nhl_id is not None and identity == candidate.nhl_id
    expected_slug = build_player_slug(f"{candidate.first_name} {candidate.last_name}")
    page_slug = clean_text(player.get("slug")).lower()
    name_slug = build_player_slug(clean_text(player.get("name")))
    url_slug = url.rstrip("/").rsplit("/", 1)[-1].lower()
    if expected_slug == "" or name_slug != expected_slug or page_slug != url_slug:
        return False
    if url_slug != expected_slug and not url_slug.startswith(f"{expected_slug}-"):
        return False
    try:
        stats = extract_mapping_rows(player.get("stats", []))
    except CapSpaceParseError:
        return False
    seasons = {
        year for row in stats if (year := resolve_nhl_stat_season(row)) is not None
    }
    return len(seasons.intersection(candidate.missing_seasons)) > 0


def resolve_nhl_stat_season(row: dict[str, object]) -> int | None:
    if clean_text(row.get("league")).upper() != "NHL":
        return None
    games = clean_text(row.get("gp"))
    found = re.match(
        r"(\d{4})", clean_text(row.get("season", row.get("platformSeason")))
    )
    if found is None or not games.isdigit() or int(games) <= 0:
        return None
    return int(found.group(1))


def are_contracts_compatible(
    existing: StoredContract, incoming: ParsedContract, team_id: int | None
) -> bool:
    if (
        existing.signing_team_id is not None
        and team_id is not None
        and existing.signing_team_id != team_id
    ):
        return False
    if (
        existing.total_value_cents is not None
        and incoming.total_value_cents is not None
        and existing.total_value_cents != incoming.total_value_cents
    ):
        return False
    return True


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractReconciliationPolicy:
    player_id: int
    incoming: ParsedContract
    signing_team_id: int | None

    def find_violation(
        self, matches: tuple[StoredContract, ...]
    ) -> ContractConflictError | None:
        if len(matches) > 1:
            return ContractConflictError(
                player_id=self.player_id, reason=ReconciliationFailure.AMBIGUOUS
            )
        if len(matches) == 0:
            return None
        existing = matches[0]
        if existing.player_id != self.player_id:
            return ContractConflictError(
                player_id=self.player_id, reason=ReconciliationFailure.FOREIGN_PLAYER
            )
        if not are_contracts_compatible(existing, self.incoming, self.signing_team_id):
            return ContractConflictError(
                player_id=self.player_id, reason=ReconciliationFailure.INCOMPATIBLE
            )
        return None

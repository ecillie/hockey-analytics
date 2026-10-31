"""Status precedence and conservative behavior when a feed is incomplete."""

from collections.abc import Mapping
from app.ScriptingFiles.FullDataScript.roster_status.domain import (
    ExternalRosterPlayer,
    FetchResult,
    RosterStatus,
    StoredPlayer,
)


def classify_player(
    player: StoredPlayer,
    ltir_player_ids: frozenset[int],
    nhl_ids: frozenset[str],
    nhl_result: FetchResult,
    ahl_result: FetchResult,
    ahl_matches: Mapping[int, ExternalRosterPlayer],
) -> RosterStatus | None:
    if player.id in ltir_player_ids:
        return RosterStatus.LTIR
    if player.nhl_external_id is not None and player.nhl_external_id in nhl_ids:
        return RosterStatus.ACTIVE
    if nhl_result.complete and player.id in ahl_matches:
        return RosterStatus.MINORS
    if (
        nhl_result.complete
        and ahl_result.complete
        and player.nhl_external_id is not None
    ):
        return RosterStatus.UNKNOWN
    return None

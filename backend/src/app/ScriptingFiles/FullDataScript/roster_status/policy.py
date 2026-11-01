"""Status precedence and conservative behavior when a feed is incomplete."""

from app.ScriptingFiles.FullDataScript.roster_status.domain import (
    RosterEvidence,
    RosterStatus,
    StoredPlayer,
)


def classify_player(
    player: StoredPlayer,
    evidence: RosterEvidence,
) -> RosterStatus | None:
    if player.id in evidence.ltir_player_ids:
        return RosterStatus.LTIR
    if (
        player.nhl_external_id is not None
        and player.nhl_external_id in evidence.nhl_external_ids
    ):
        return RosterStatus.ACTIVE
    if evidence.nhl_complete and player.id in evidence.ahl_player_ids:
        return RosterStatus.MINORS
    if (
        evidence.nhl_complete
        and evidence.ahl_complete
        and player.nhl_external_id is not None
    ):
        return RosterStatus.UNKNOWN
    return None

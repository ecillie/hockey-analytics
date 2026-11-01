"""Compatibility boundaries for canonical active contract persistence."""

from collections.abc import Mapping
from psycopg2.extensions import cursor as PgCursor
from app.ScriptingFiles.FullDataScript.contracts.domain import (
    ActivePlayer,
    ContractSeason,
    ParsedContract,
    ActiveContractWrite,
    ActiveSeasonWrite,
)
from app.ScriptingFiles.FullDataScript.contracts.repository import active

from app.ScriptingFiles.FullDataScript.contracts.repository.active import (
    ActiveContractCounts,
    resolve_active_player as resolve_active_player,
    save_active_snapshot as save_active_snapshot,
    ActiveContractRepository as ActiveContractRepository,
    PostgresActiveContractRepository as PostgresActiveContractRepository,
    ActiveRepositoryFactory as ActiveRepositoryFactory,
    open_active_repository as open_active_repository,
    ContextualActiveRepositoryFactory as ContextualActiveRepositoryFactory,
)


def upsert_active_season(
    cursor: PgCursor,
    *,
    contract_id: int,
    external_id: str,
    owning_team_id: int | None,
    detail: ContractSeason,
) -> int:
    return active.upsert_active_season(
        cursor,
        ActiveSeasonWrite(
            contract_id=contract_id,
            external_id=external_id,
            owning_team_id=owning_team_id,
            detail=detail,
        ),
    )


def upsert_active_contract(
    cursor: PgCursor,
    *,
    player_id: int,
    source_id: int,
    item: ActivePlayer,
    contract: ParsedContract,
    index: int,
    team_ids: Mapping[str, int],
) -> ActiveContractCounts:
    return active.upsert_active_contract(
        cursor,
        ActiveContractWrite(
            player_id=player_id,
            source_id=source_id,
            item=item,
            contract=contract,
            index=index,
            signing_team_id=team_ids.get(
                str(
                    contract.signing_team
                    if contract.signing_team is not None
                    else item.team
                ).upper()
            ),
            owning_team_id=team_ids.get(item.team),
        ),
    )

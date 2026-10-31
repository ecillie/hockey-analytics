"""Compatibility serialization for persisted contract source records."""

from dataclasses import asdict

from app.ScriptingFiles.FullDataScript.contracts.domain import (
    ParsedContract,
    ContractSeason,
)


def serialize_contract(contract: ParsedContract) -> dict[str, object]:
    payload = asdict(contract)
    payload.pop("source_snapshot")
    payload["source_payload"] = contract.source_payload
    payload["seasons"] = tuple(map(serialize_season, contract.seasons))
    return payload


def serialize_season(season: ContractSeason) -> dict[str, object]:
    payload = asdict(season)
    payload.pop("source_snapshot")
    payload["source_payload"] = season.source_payload
    return payload

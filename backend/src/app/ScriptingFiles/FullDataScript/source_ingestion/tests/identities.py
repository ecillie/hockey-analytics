"""Equivalent numeric player IDs and their original source snapshots."""

from dataclasses import dataclass

from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy

from app.ScriptingFiles.FullDataScript.source_ingestion.util import source_row_hash
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    PlayerKind,
    StatLayout,
    stat_layout,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.nhl.domain import StatsJob
from app.ScriptingFiles.FullDataScript.source_ingestion.policy import RowPolicy

type SourceRows = tuple[dict[str, object], ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class IdentityKind:
    job: StatsJob
    advanced: StatLayout
    basic: StatLayout


@dataclass(slots=True, kw_only=True, frozen=True)
class IdentityRows:
    player_id: int
    moneypuck: SourceRows
    nhl: SourceRows
    moneypuck_hashes: tuple[str, ...]
    nhl_hashes: tuple[str, ...]
    policy: RowPolicy
    kinds: tuple[IdentityKind, ...]


def build_identity_rows(player_id: int) -> IdentityRows:
    representations = (
        player_id,
        float(player_id),
        f"{player_id:012d}",
        f"{player_id}.0",
        f"{player_id}e0",
    )
    moneypuck: SourceRows = tuple(
        {
            "playerId": value,
            "season": 2025,
            "name": "Test Player",
            "team": "AAA",
            "situation": "all",
            "games_played": 10,
            "icetime": 1200,
        }
        for value in representations
    )
    nhl: SourceRows = tuple(
        {
            "playerId": value,
            "skaterFullName": "Test Player",
            "goalieFullName": "Test Player",
            "teamAbbrevs": "AAA",
            "gamesPlayed": 10,
            "goals": 1,
            "assists": 2,
            "points": 3,
            "shotsAgainst": 100,
            "saves": 95,
            "goalsAgainst": 5,
        }
        for value in representations
    )
    return IdentityRows(
        player_id=player_id,
        policy=RowPolicy(
            source="MoneyPuck",
            required_fields=("playerId", "season"),
            grain_fields=("playerId", "season", "team", "situation"),
            integer_fields=frozenset({"playerId", "season"}),
        ),
        kinds=tuple(
            IdentityKind(
                job=StatsJob(kind=kind, season=2025, game_type=2),
                advanced=stat_layout(kind, advanced=True),
                basic=stat_layout(kind, advanced=False),
            )
            for kind in PlayerKind
        ),
        moneypuck=moneypuck,
        nhl=nhl,
        moneypuck_hashes=tuple(map(source_row_hash, moneypuck)),
        nhl_hashes=tuple(map(source_row_hash, nhl)),
    )


def equivalent_identity_rows() -> SearchStrategy[IdentityRows]:
    return st.integers(min_value=-999_999_999, max_value=999_999_999).map(
        build_identity_rows
    )

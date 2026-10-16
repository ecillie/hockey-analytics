from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

import pandas as pd
import pytest

from app.api import schemas
from app.api.service import TradeValueService, _identity, _summary
from app.jobs.shared.consumer_contracts import ENDPOINT_QUERIES, QUERY_CONTRACTS, validate_query_row
from ml.features.build_features import build_features
from ml.pipelines import build_model_dataset as model_dataset

from .test_api_service import Result, ScriptedSession


FIXTURE_DIR = Path(__file__).parent / "fixtures/data_contracts"
ROWS = json.loads((FIXTURE_DIR / "query_rows.json").read_text())


def row(query):
    value = deepcopy(ROWS[query])
    for field in ("birth_date", "signed_on"):
        if value.get(field) is not None:
            value[field] = date.fromisoformat(value[field])
    return validate_query_row(query, value).model_dump()


@pytest.mark.parametrize("query", QUERY_CONTRACTS)
def test_each_consumer_query_result_has_a_valid_fixture(query):
    assert set(ROWS) == set(QUERY_CONTRACTS)
    assert row(query)


def test_every_existing_endpoint_has_query_contracts():
    root = Path(__file__).resolve().parents[2]
    openapi = json.loads((root / "docs/openapi.json").read_text())
    assert set(openapi["paths"]) == {"/api" + path for path in ENDPOINT_QUERIES}
    assert all(set(names) <= set(QUERY_CONTRACTS) for names in ENDPOINT_QUERIES.values())


def test_query_fixtures_feed_the_existing_public_identity_and_summary():
    identity = schemas.PlayerIdentity.model_validate(_identity(row("player_identity")))
    summary = schemas.PlayerSummary.model_validate(_summary(row("player_summary")))
    assert identity.id == summary.id == 7
    assert summary.toiSeconds == 3600
    assert summary.capHitCents == 800_000_000
    assert summary.projectedNextSeasonHockeyValue == 2.25


def test_nullable_columns_must_be_present_and_zero_is_retained():
    value = row("player_summary")
    value.update(goals=0, assists=None, points=None, ice_time_seconds=None, cap_hit_cents=None)
    checked = validate_query_row("player_summary", value)
    public = schemas.PlayerSummary.model_validate(_summary(checked.model_dump()))
    assert public.goals == 0 and public.assists is None and public.toiSeconds is None
    del value["assists"]
    with pytest.raises(ValueError):
        validate_query_row("player_summary", value)


def test_goalie_contract_and_salary_queries_feed_unchanged_services(monkeypatch):
    service = TradeValueService(ScriptedSession(Result(rows=[row("goalie_stats")])))
    goalie = schemas.GoalieStats.model_validate(service._goalie_stats(8, 2025))
    assert goalie.goalsSavedAboveExpected == 5.0
    contract_season = row("contract_season")
    # The existing SQL NUMERIC value is a Decimal; cents remain integer values.
    contract_season["cap_percentage"] = Decimal("0.08376963")
    validate_query_row("contract_season", contract_season)
    service = TradeValueService(ScriptedSession(Result(rows=[row("contract")]), Result(rows=[contract_season])))
    monkeypatch.setattr(service, "player_identity", lambda *_: _identity(row("player_identity")))
    monkeypatch.setattr(service, "current_season", lambda: 2025)
    contract = schemas.Contract.model_validate(service.contract(7))
    assert contract.playerId == 7 and contract.seasons[0].capHitCents == 800_000_000
    assert contract.seasons[0].capPercentage == pytest.approx(0.08376963)
    service = TradeValueService(ScriptedSession(Result(rows=[row("team_cap")])))
    monkeypatch.setattr(service, "require_season", lambda *_: None)
    monkeypatch.setattr(service, "team_summary", lambda *_: {})
    cap = schemas.TeamCap.model_validate(service.team_cap(10, 2025))
    assert cap.capSpaceCents == 8_750_000_000 and cap.calculationStatus == "ESTIMATE"


def test_ml_projection_grain_units_and_missingness_match_existing_readers(monkeypatch):
    players = pd.DataFrame([row("ml_player_season")])
    cap = pd.DataFrame([row("ml_salary_cap")])
    monkeypatch.setattr(model_dataset, "load_player_stats", lambda **_: players)
    monkeypatch.setattr(model_dataset, "load_salary_cap", lambda: cap)
    dataset = model_dataset.build_model_dataset()
    assert len(dataset) == 1 and dataset.iloc[0]["position_group"] == "forward"
    assert dataset.iloc[0]["salary_cap_fraction"] == 0.955
    assert not model_dataset.FORBIDDEN_CONTRACT_COLUMNS.intersection(dataset.columns)
    features = build_features(dataset)
    assert features.iloc[0]["xg_per_60"] == pytest.approx(18.5 * 3600 / 3600.4)
    players.loc[0, "ice_time_seconds"] = None
    players.loc[0, "game_score"] = None
    assert pd.isna(build_features(model_dataset.build_model_dataset()).iloc[0]["game_score_per_60"])


def test_ml_duplicate_seasons_and_contract_leakage_are_blocked(monkeypatch):
    players = pd.DataFrame([row("ml_player_season")])
    monkeypatch.setattr(model_dataset, "load_player_stats", lambda **_: pd.concat([players, players]))
    monkeypatch.setattr(model_dataset, "load_salary_cap", lambda: pd.DataFrame([row("ml_salary_cap")]))
    with pytest.raises(RuntimeError, match="duplicate player-season"):
        model_dataset.build_model_dataset()
    players["cap_hit_cents"] = 800_000_000
    monkeypatch.setattr(model_dataset, "load_player_stats", lambda **_: players)
    with pytest.raises(RuntimeError, match="Contract data leaked"):
        model_dataset.build_model_dataset()
    with pytest.raises(ValueError):
        validate_query_row("ml_player_season", row("ml_player_season") | {"position": "G"})

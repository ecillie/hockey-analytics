"""Model dataset orchestration with explicit reader and frame ownership."""

import pandas as pd

from ml.domain import FeatureOptions
from ml.errors import MinimumGamesError, ContractLeakageError, FrameGrainError
from ml.features.util import group_player_positions
from ml.pipelines.repository import ModelDataReader, open_model_data_reader
from ml.schemas import validate_feature_options, validate_frame


FORBIDDEN_CONTRACT_COLUMNS = frozenset(
    {
        "contract_id",
        "contract_type",
        "average_value_cents",
        "cap_hit_cents",
        "cap_percentage",
        "actual_cap_hit",
        "aav",
    }
)


def build_model_dataset(
    min_games: int = 1,
    *,
    players: pd.DataFrame | None = None,
    salary_cap: pd.DataFrame | None = None,
    options: FeatureOptions | None = None,
    reader: ModelDataReader | None = None,
) -> pd.DataFrame:

    selected = options or FeatureOptions()
    validate_feature_options(selected)
    if min_games < 1:
        raise MinimumGamesError(field="min_games", value=min_games)
    if reader is not None:
        return assemble_model_dataset(
            players=reader.read_players(min_games) if players is None else players,
            salary_cap=reader.read_salary_caps() if salary_cap is None else salary_cap,
            min_games=min_games,
            options=selected,
        )
    if players is None or salary_cap is None:
        with open_model_data_reader() as owned:
            return build_model_dataset(
                min_games,
                players=players,
                salary_cap=salary_cap,
                options=selected,
                reader=owned,
            )
    return assemble_model_dataset(
        players=players, salary_cap=salary_cap, min_games=min_games, options=selected
    )


def assemble_model_dataset(
    *,
    players: pd.DataFrame,
    salary_cap: pd.DataFrame,
    min_games: int,
    options: FeatureOptions,
) -> pd.DataFrame:
    validate_frame(
        players,
        required=("player_id", "season", "position", "games_played"),
        grain=("player_id", "season"),
    )
    validate_frame(
        salary_cap,
        required=("season", "season_label", "salary_cap_cents", "salary_cap_dollars"),
        grain=("season",),
    )
    players = players.loc[players["games_played"].fillna(0) >= min_games].copy()

    df = players.merge(
        salary_cap[
            [
                "season",
                "season_label",
                "salary_cap_cents",
                "salary_cap_dollars",
            ]
        ],
        how="left",
        on="season",
        validate="many_to_one",
    )

    df["position_group"] = group_player_positions(df["position"])
    df["salary_cap_fraction"] = (
        df["salary_cap_dollars"] / options.salary_cap_normalization_dollars
    )

    duplicate_count = df.duplicated(subset=["player_id", "season"]).sum()

    if duplicate_count:
        raise FrameGrainError(grain=("player_id", "season"))

    leaked_columns = FORBIDDEN_CONTRACT_COLUMNS.intersection(df.columns)

    if leaked_columns:
        raise ContractLeakageError(columns=tuple(sorted(leaked_columns)))

    return df.reset_index(drop=True)


def run_pipeline(
    min_games: int = 1,
    *,
    players: pd.DataFrame | None = None,
    salary_caps: pd.DataFrame | None = None,
    reader: ModelDataReader | None = None,
) -> pd.DataFrame:
    return build_model_dataset(
        min_games, players=players, salary_cap=salary_caps, reader=reader
    )

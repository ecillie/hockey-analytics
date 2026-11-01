"""Shared position grouping at the dataframe boundary."""

import pandas as pd

from ml.domain import SkaterPosition


def group_player_positions(positions: pd.Series) -> pd.Series:
    return positions.map(
        {position.name: position.group.value for position in SkaterPosition}
    )


def calculate_per_60(
    values: pd.Series,
    ice_time_seconds: pd.Series,
) -> pd.Series:
    valid_toi = ice_time_seconds.where(ice_time_seconds > 0)

    return values.astype(float) * 3600.0 / valid_toi

"""Training orchestration over owned frames and sklearn model resources."""

import numpy as np
import pandas as pd
from app.shared.observability.domain import (
    InvocationContext,
    LogLevel,
)
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from ml.domain import ArtifactPaths
from ml.repository import save_model
from ml.domain import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    FeatureOptions,
    ModelOptions,
)
from ml.evaluation.util import (
    split_temporal_data,
    validate_metadata,
)
from ml.features.services import (
    calculate_replacement_level,
)
from ml.schemas import SplitMetrics, validate_frame
from ml.domain import Split
from ml.errors import TrainingRowsError, TrainingTargetsError
from ml.observability.services import report_ml_progress


from ml.training.domain import TrainingResult


def build_training_data(
    df: pd.DataFrame | None = None, *, options: FeatureOptions | None = None
) -> pd.DataFrame:

    all_rows = calculate_replacement_level(df, options=options)
    if all_rows.empty:
        raise TrainingRowsError(rows=len(all_rows))

    all_rows["hockey_value"] = (
        all_rows["game_score_per_60_above_replacement"] * all_rows["toi_hours"]
    )

    targets = all_rows[
        [
            "player_id",
            "season",
            "hockey_value",
        ]
    ].copy()

    targets = targets.rename(
        columns={
            "season": "target_season",
            "hockey_value": "next_season_hockey_value",
        }
    )

    df = all_rows[
        all_rows["eligible_for_training"] & all_rows["position_group"].notna()
    ].copy()

    df["current_hockey_value"] = (
        df["game_score_per_60_above_replacement"] * df["toi_hours"]
    )

    df["target_season"] = df["season"] + 1

    df = df.merge(
        targets,
        how="left",
        on=[
            "player_id",
            "target_season",
        ],
        validate="one_to_one",
    )

    latest_season = int(all_rows["season"].max())

    df = df[df["target_season"] <= latest_season].copy()

    df["next_season_hockey_value"] = df["next_season_hockey_value"].fillna(0.0)

    df.replace(
        [np.inf, -np.inf],
        np.nan,
        inplace=True,
    )

    return df.reset_index(drop=True)


def build_model(options: ModelOptions | None = None) -> Pipeline:
    selected = options or ModelOptions()
    numeric_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(strategy="median"),
            ),
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(strategy="most_frequent"),
            ),
            (
                "one_hot",
                OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=False,
                ),
            ),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "numeric",
                numeric_pipeline,
                list(NUMERIC_FEATURES),
            ),
            (
                "categorical",
                categorical_pipeline,
                list(CATEGORICAL_FEATURES),
            ),
        ]
    )

    regressor = HistGradientBoostingRegressor(
        learning_rate=selected.learning_rate,
        max_iter=selected.max_iter,
        max_leaf_nodes=selected.max_leaf_nodes,
        l2_regularization=selected.l2_regularization,
        random_state=selected.random_state,
    )

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", regressor),
        ]
    )


def evaluate_training_split(
    model: Pipeline,
    df: pd.DataFrame,
) -> SplitMetrics:

    X = df[list(NUMERIC_FEATURES + CATEGORICAL_FEATURES)]

    y = df["next_season_hockey_value"]

    predictions = model.predict(X)

    mae = mean_absolute_error(
        y,
        predictions,
    )

    rmse = np.sqrt(
        mean_squared_error(
            y,
            predictions,
        )
    )

    r2 = r2_score(
        y,
        predictions,
    )

    return SplitMetrics(rows=len(df), mae=float(mae), rmse=float(rmse), r2=float(r2))


def train_model(
    data: pd.DataFrame,
    *,
    options: ModelOptions | None = None,
    context: InvocationContext | None = None,
) -> TrainingResult:
    validate_frame(
        data,
        required=(
            "player_id",
            "season",
            "target_season",
            "next_season_hockey_value",
            *NUMERIC_FEATURES,
            *CATEGORICAL_FEATURES,
        ),
        grain=("player_id", "season"),
    )
    if data["next_season_hockey_value"].isna().any():
        raise TrainingTargetsError(
            invalid_rows=int(data["next_season_hockey_value"].isna().sum())
        )
    splits = split_temporal_data(data)
    report_ml_progress(
        context,
        event="ml.dataset_validated",
        stage="training",
        values={"rows": len(data)},
    )
    for name, frame in splits.items():
        report_ml_progress(
            context,
            event="ml.split_ready",
            stage=name.value,
            values={"rows": len(frame)},
            level=LogLevel.DEBUG,
        )
    validation_season = int(splits[Split.VALIDATION]["target_season"].iloc[0])
    test_season = int(splits[Split.TEST]["target_season"].iloc[0])
    columns = list(NUMERIC_FEATURES + CATEGORICAL_FEATURES)
    model = build_model(options)
    report_ml_progress(
        context,
        event="ml.training_started",
        stage="validation_fit",
        values={"rows": len(splits[Split.TRAIN])},
    )
    model.fit(
        splits[Split.TRAIN][columns], splits[Split.TRAIN]["next_season_hockey_value"]
    )
    split_metrics = {
        name: evaluate_training_split(model, frame) for name, frame in splits.items()
    }
    for name, values in split_metrics.items():
        report_ml_progress(
            context,
            event="ml.split_evaluated",
            stage=name.value,
            values={
                "rows": values.rows,
                "mae": values.mae,
                "rmse": values.rmse,
                "r2": values.r2,
            },
        )
    final_training = data[data["target_season"] < test_season]
    final_model = build_model(options)
    report_ml_progress(
        context,
        event="ml.training_started",
        stage="final_fit",
        values={"rows": len(final_training)},
    )
    final_model.fit(final_training[columns], final_training["next_season_hockey_value"])
    report_ml_progress(
        context,
        event="ml.training_finished",
        stage="final_fit",
        values={"rows": len(final_training)},
    )
    metadata = {
        "model_type": "HistGradientBoostingRegressor",
        "target": "next_season_hockey_value",
        "target_definition": (
            "next-season game_score_per_60_above_replacement "
            "multiplied by next-season TOI hours"
        ),
        "contract_features_used": False,
        "numeric_features": list(NUMERIC_FEATURES),
        "categorical_features": list(CATEGORICAL_FEATURES),
        "validation_target_season": validation_season,
        "test_target_season": test_season,
        "metrics": split_metrics,
    }
    return TrainingResult(model=final_model, metadata_value=validate_metadata(metadata))


def train_skater_model(
    df: pd.DataFrame | None = None,
    *,
    paths: ArtifactPaths | None = None,
    options: ModelOptions | None = None,
    context: InvocationContext | None = None,
) -> Pipeline:
    data = build_training_data(df)
    report_ml_progress(
        context, event="ml.dataset_ready", stage="training", values={"rows": len(data)}
    )
    result = train_model(data, options=options, context=context)
    if paths is not None:
        save_model(result.model, result.metadata_value, paths, context=context)
    return result.model

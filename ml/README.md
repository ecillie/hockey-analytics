# ML pipeline boundaries

Run `uv run python -m ml.pipelines.run_pipeline` to load each data source once
and print dataset diagnostics. `run_pipeline(players=..., salary_caps=...)`
uses caller-provided frames without opening a database. The SQL loaders also
accept a borrowed SQLAlchemy `connection`; they close only resources they own.

`build_features(frame)`, `calculate_replacement_level(frame)`, and
`build_training_data(frame)` return new frames. Inputs require the documented
player-season grain, required columns, and finite numeric values; missing
performance observations remain nullable for the existing imputation policy.
Feature lists are immutable tuples in `ml.configuration`. `FeatureOptions`
and `ModelOptions` own configurable defaults; the default model, percentile,
training eligibility, target joins, chronological splits, and seed are preserved.

`train_model(training_data)` returns the fitted model and canonical metadata
without console output or artifact writes. `train_skater_model(frame)` likewise computes
only; pass `paths=ArtifactPaths(model=..., metadata=...)` to persist explicitly.
`save_model` validates metadata before writing, and `load_model` validates it
before loading the estimator. Model metadata preserves JSON lists and sorted,
indented serialization, with a final newline.

`evaluate_training_split` computes typed split metrics and
`calculate_prediction_metrics` computes evaluation diagnostics. Existing
`train`, `evaluate`, and `metrics` imports remain direct aliases to these
functions, with the same arguments and results.

`evaluate_predictions(model, metadata, training_data)` computes raw model and
benchmark evaluation columns without I/O. `prediction_frame` provides the
public player/season/prediction shape and clips negative predictions to zero.
Raw evaluation predictions remain unclipped so the existing metric meaning is
preserved. `evaluate_model(paths, data=..., output=...)` combines explicit
artifact loading with optional CSV output. Console diagnostics are separate.

The training and evaluation module commands resolve their default output paths
only at invocation, honoring `TRADEVALUE_MODEL_DIR` and
`TRADEVALUE_EVALUATION_DIR`. Importing the computation modules does not discover
artifact paths. No published model is retrained or replaced by the test suite.

Validate with `uv run pytest --no-cov -q tests/ml` and
`uv run python -m ml.evaluation.gate`.

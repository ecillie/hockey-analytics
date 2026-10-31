#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
package_scratch=$(mktemp -d)
trap 'rm -rf "$package_scratch"' EXIT
uv build --package tradevalue-backend --wheel --out-dir "$package_scratch/wheels"
uv build --package tradevalue-ml --wheel --out-dir "$package_scratch/wheels"
unzip -Z1 "$package_scratch"/wheels/tradevalue_backend-*.whl > "$package_scratch/api-files"
unzip -Z1 "$package_scratch"/wheels/tradevalue_ml-*.whl > "$package_scratch/ml-files"
if grep -E 'ScriptingFiles|(^|/)(tests|data|ml)/|\.csv$|\.joblib$|\.pyc$' "$package_scratch/api-files"; then exit 1; fi
if grep -E '(^|/)(tests|outputs)/|\.csv$|\.joblib$|\.pyc$' "$package_scratch/ml-files"; then exit 1; fi
grep -E '^app/main.py$' "$package_scratch/api-files"
grep -E '^ml/resources/skater_value_model_metadata.json$' "$package_scratch/ml-files"
uv venv --python 3.12 "$package_scratch/environment"
uv pip install --python "$package_scratch/environment/bin/python" -r backend/requirements-dev.txt "$package_scratch"/wheels/*.whl
cd "$package_scratch"
env -u PYTHONPATH -u TRADEVALUE_MODEL_DIR uv run --no-project --python "$package_scratch/environment/bin/python" python -c 'import app.main, ml.features.build_features; from pathlib import Path; from ml.paths import artifact_directory; assert artifact_directory("TRADEVALUE_MODEL_DIR", Path("models")) == Path.cwd().joinpath("ml", "models"); print(app.main.__file__); print(ml.features.build_features.__file__)'
uv run --no-project --python "$package_scratch/environment/bin/python" python -m ml.evaluation.gate

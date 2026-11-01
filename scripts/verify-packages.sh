#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
package_scratch=$(mktemp -d)
trap 'rm -rf "$package_scratch"' EXIT
uv build --package tradevalue-backend --out-dir "$package_scratch/wheels"
uv build --package tradevalue-ml --out-dir "$package_scratch/wheels"
unzip -Z1 "$package_scratch"/wheels/tradevalue_backend-*.whl > "$package_scratch/api-files"
unzip -Z1 "$package_scratch"/wheels/tradevalue_ml-*.whl > "$package_scratch/ml-files"
tar -tzf "$package_scratch"/wheels/tradevalue_backend-*.tar.gz >> "$package_scratch/api-files"
tar -tzf "$package_scratch"/wheels/tradevalue_ml-*.tar.gz >> "$package_scratch/ml-files"
if grep -E 'ScriptingFiles|(^|/)(tests|data|ml)/|\.csv$|\.joblib$|\.pyc$|/\.env' "$package_scratch/api-files"; then exit 1; fi
if grep -E '(^|/)(tests|outputs)/|\.csv$|\.joblib$|\.pyc$|/\.env' "$package_scratch/ml-files"; then exit 1; fi
grep -E '^app/main.py$' "$package_scratch/api-files"
grep -E '^app/shared/observability/(domain|formatting|policy|services|sinks).py$' "$package_scratch/api-files"
grep -E '^ml/resources/skater_value_model_metadata.json$' "$package_scratch/ml-files"
uv venv --python 3.12 "$package_scratch/api-environment"
uv venv --python 3.12 "$package_scratch/ml-environment"
uv venv --python 3.12 "$package_scratch/vercel-environment"
vercel_install_command=$(jq -er '.installCommand' backend/vercel.json)
(cd backend; VIRTUAL_ENV="$package_scratch/vercel-environment" sh -c "$vercel_install_command")
grep -v '^\.$' backend/requirements.txt > "$package_scratch/api-requirements.txt"
uv pip install --python "$package_scratch/api-environment/bin/python" -r "$package_scratch/api-requirements.txt" "$package_scratch"/wheels/tradevalue_backend-*.whl
uv pip install --python "$package_scratch/ml-environment/bin/python" -r ml/requirements.txt "$package_scratch"/wheels/*.whl
cd "$package_scratch"
env -u PYTHONPATH uv run --no-project --python "$package_scratch/vercel-environment/bin/python" python -c 'import importlib.util; from pathlib import Path; import app.main; assert len(app.main.create_app().openapi()["paths"]) == 18; assert Path(app.main.__file__).resolve().is_relative_to(Path.cwd().joinpath("vercel-environment").resolve()); assert all(importlib.util.find_spec(name) is None for name in ("app.shared.observability.tests", "app.ScriptingFiles", "ml", "pandas", "sklearn", "requests", "pytest", "hypothesis")); print(app.main.__file__)'
env -u PYTHONPATH uv run --no-project --python "$package_scratch/api-environment/bin/python" python -c 'import importlib.util; from app.shared.observability.domain import read_logging_settings; from app.shared.observability.formatting import SafeFormatter; assert read_logging_settings({}).level.name == "INFO"; assert importlib.util.find_spec("app.shared.observability.tests") is None; print(SafeFormatter.__module__)'
env -u PYTHONPATH uv run --no-project --python "$package_scratch/ml-environment/bin/python" python -c 'from app.shared.observability.domain import read_logging_settings; from app.shared.observability.sinks import build_diagnostic_handler; assert read_logging_settings({"LOG_LEVEL": "DEBUG"}).level.name == "DEBUG"; print(build_diagnostic_handler.__module__)'
env -u PYTHONPATH uv run --no-project --python "$package_scratch/api-environment/bin/python" python -c 'import importlib.util; import app.main; assert len(app.main.create_app().openapi()["paths"]) == 18; assert all(importlib.util.find_spec(name) is None for name in ("app.api.tests", "app.ScriptingFiles", "pandas", "sklearn", "requests", "pytest", "hypothesis")); print(app.main.__file__)'
env -u PYTHONPATH -u TRADEVALUE_MODEL_DIR uv run --no-project --python "$package_scratch/ml-environment/bin/python" python -c 'import importlib.util; import app.main, ml.features.build_features; from pathlib import Path; from ml.paths import artifact_directory; assert all(importlib.util.find_spec(name) is None for name in ("ml.tests", "pytest", "hypothesis")); assert artifact_directory("TRADEVALUE_MODEL_DIR", Path("models")) == Path.cwd().joinpath("ml", "models"); print(ml.features.build_features.__file__)'
uv run --no-project --python "$package_scratch/ml-environment/bin/python" python -m ml.evaluation.gate

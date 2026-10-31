#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export_args=(--locked --no-hashes --no-header --no-annotate --no-emit-project)
export_file() {
  local target="$1"
  shift
  if [[ "${check_exports}" == true ]]; then
    uv export "${export_args[@]}" "$@" | diff -u "$target" -
  else
    uv export "${export_args[@]}" "$@" --output-file "$target" > /dev/null
  fi
}
check_exports=false
if [[ "${1:-}" == --check ]]; then check_exports=true; fi
export_file backend/requirements.txt --no-default-groups
export_file backend/requirements-dev.txt --all-groups
export_file ml/requirements.txt --only-group ml

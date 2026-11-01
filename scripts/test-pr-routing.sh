#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
routing_scratch=$(mktemp -d)
trap 'rm -rf "$routing_scratch"' EXIT
awk '
  /^        run: \|$/ { in_script=1; next }
  in_script {
    sub(/^          /, "")
    gsub(/\$\{\{ github.repository \}\}/, "ecillie/hockey-analytics")
    print
  }
' .github/workflows/route-pr.yml > "$routing_scratch/router.sh"
test -s "$routing_scratch/router.sh"
bash -n "$routing_scratch/router.sh"
cat > "$routing_scratch/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
if [ "$1" = api ]; then
  printf '%s\n' "$ROUTE_TEST_BRANCHES"
  exit 0
fi
if [ "$1" = pr ] && [ "$2" = edit ]; then
  printf '%s\n' "$*" >> "$ROUTE_TEST_LOG"
  exit 0
fi
exit 99
STUB
chmod +x "$routing_scratch/gh"

assert_route() {
  local head="$1" base="$2" title="$3" expected="$4"
  local branches="${5-Release-1.9.0
Release-1.10.0
Hotfix-1.0.2}"
  : > "$routing_scratch/edits"
  if ! env PATH="$routing_scratch:$PATH" PR_NUMBER=42 PR_HEAD="$head" \
      PR_BASE="$base" PR_TITLE="$title" ROUTE_TEST_BRANCHES="$branches" \
      ROUTE_TEST_LOG="$routing_scratch/edits" \
      bash "$routing_scratch/router.sh" > "$routing_scratch/output" 2>&1; then
    cat "$routing_scratch/output"
    return 1
  fi
  local actual
  actual=$(cat "$routing_scratch/edits")
  if [ "$expected" = unchanged ]; then
    test -z "$actual"
  else
    test "$actual" = "pr edit 42 --repo ecillie/hockey-analytics --base $expected"
  fi
  printf 'PASS %s -> %s (%s)\n' "$head" "$expected" "$title"
}

assert_route feature/example Dev 'Add player search' unchanged
assert_route feature/example Release-1.10.0 'Add player search' Dev
assert_route feature/example Prod 'Add player search' Dev
assert_route feature/example Hotfix-1.0.2 'Hotfix: Fix cap calculation' Dev
assert_route feature/example Release-1.10.0 'Fix hotfix regression' Dev
assert_route API-Setup Release-1.10.0 'Update API' Dev
assert_route feature/example Release-1.10.0 'No release branch required' Dev ''
assert_route Dev Dev 'Promote Dev to Release-1.10.0' Release-1.10.0
assert_route Dev Release-1.10.0 'Promote Dev to Release-1.10.0' unchanged
assert_route Release-1.10.0 Prod 'Promote Release-1.10.0 to Prod' unchanged
assert_route Hotfix-1.0.2 Prod 'Promote Hotfix-1.0.2 to Prod' unchanged

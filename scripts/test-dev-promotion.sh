#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
promotion_scratch=$(mktemp -d)
trap 'rm -rf "$promotion_scratch"' EXIT
bash -n scripts/promote-dev.sh
cat > "$promotion_scratch/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$TEST_CALLS"
if [ "$1" = api ]; then
  if [[ "$2" == */branches ]]; then
    if [ "$TEST_BRANCH_FAILURE" = true ]; then exit 17; fi
    printf '%s\n' "$TEST_BRANCHES"
    exit 0
  fi
  if [[ "$2" == */compare/* ]]; then
    printf '%s\n' "$TEST_AHEAD"
    exit 0
  fi
fi
if [ "$1" = pr ] && [ "$2" = list ]; then
  query=''
  while [ "$#" -gt 0 ]; do
    if [ "$1" = --jq ]; then query="$2"; shift 2; else shift; fi
  done
  jq -r "$query" <<< "$TEST_EXISTING"
  exit 0
fi
if [ "$1" = pr ] && [ "$2" = view ]; then
  if [[ "$*" == *autoMergeRequest* ]]; then
    printf '%s\n' "$TEST_AUTO"
  else
    printf '%s\n' "$TEST_TITLE"
  fi
  exit 0
fi
if [ "$1" = pr ] && [[ "$2" == create || "$2" == edit || "$2" == merge ]]; then
  printf '%s\n' "$*" >> "$TEST_MUTATIONS"
  exit 0
fi
exit 99
STUB
chmod +x "$promotion_scratch/gh"

reset_scenario() {
  branches='Release-1.9.0
Release-1.10.0
Release-latest
Hotfix-1.9.0
Hotfix-1.10.0'
  existing='[]'
  title=''
  auto=false
  ahead=3
  source_branch=Dev
  branch_failure=false
}

run_case() {
  local name="$1" kind="$2" expected_status="${3:-0}" status=0
  : > "$promotion_scratch/calls"
  : > "$promotion_scratch/mutations"
  env PATH="$promotion_scratch:$PATH" GITHUB_REPOSITORY=ecillie/hockey-analytics \
    GITHUB_REF_NAME="$source_branch" PROMOTION_TYPE="$kind" \
    TEST_BRANCHES="$branches" TEST_EXISTING="$existing" TEST_TITLE="$title" \
    TEST_AUTO="$auto" TEST_AHEAD="$ahead" TEST_BRANCH_FAILURE="$branch_failure" \
    TEST_CALLS="$promotion_scratch/calls" TEST_MUTATIONS="$promotion_scratch/mutations" \
    bash scripts/promote-dev.sh > "$promotion_scratch/output" 2>&1 || status=$?
  if [ "$status" -ne "$expected_status" ]; then
    cat "$promotion_scratch/output"
    echo "FAIL $name: expected status $expected_status, got $status" >&2
    exit 1
  fi
  printf 'PASS %s\n' "$name"
}

assert_mutation() {
  grep -F -- "$1" "$promotion_scratch/mutations" > /dev/null
}

assert_no_mutations() {
  test ! -s "$promotion_scratch/mutations"
}

reset_scenario
run_case normal-release release
assert_mutation 'pr create --repo ecillie/hockey-analytics --base Release-1.10.0 --head Dev --title Promote Dev to Release-1.10.0'

reset_scenario
run_case hotfix-release hotfix
assert_mutation 'pr create --repo ecillie/hockey-analytics --base Hotfix-1.10.0 --head Dev --title Hotfix: Promote Dev to Hotfix-1.10.0'

reset_scenario
existing='[{"number":42,"baseRefName":"Release-1.10.0"}]'
title='Promote Dev to Release-1.10.0'
run_case reuse-matching-promotion release
assert_no_mutations

reset_scenario
existing='[{"number":42,"baseRefName":"Release-1.10.0"}]'
title='Promote Dev to Release-1.10.0'
auto=true
run_case switch-to-hotfix hotfix
assert_mutation 'pr edit 42 --repo ecillie/hockey-analytics --base Hotfix-1.10.0 --title Hotfix: Promote Dev to Hotfix-1.10.0'
test "$(head -1 "$promotion_scratch/mutations")" = 'pr merge 42 --repo ecillie/hockey-analytics --disable-auto'
test "$(wc -l < "$promotion_scratch/mutations" | tr -d ' ')" -eq 2

reset_scenario
existing='[{"number":42,"baseRefName":"Hotfix-1.10.0"}]'
title='Hotfix: Promote Dev to Hotfix-1.10.0'
run_case switch-to-normal release
assert_mutation 'pr edit 42 --repo ecillie/hockey-analytics --base Release-1.10.0 --title Promote Dev to Release-1.10.0'
test "$(wc -l < "$promotion_scratch/mutations" | tr -d ' ')" -eq 1

reset_scenario
existing='[{"number":42,"baseRefName":"Hotfix-1.10.0"}]'
title='Incorrect title'
run_case reconcile-title hotfix
assert_mutation '--title Hotfix: Promote Dev to Hotfix-1.10.0'

reset_scenario
existing='[{"number":42,"baseRefName":"Release-1.9.0"}]'
title='Promote Dev to Release-1.9.0'
run_case select-newest-version release
assert_mutation '--base Release-1.10.0'

reset_scenario
existing='[{"number":42,"baseRefName":"Release-1.10.0"},{"number":43,"baseRefName":"Hotfix-1.10.0"}]'
run_case reject-multiple-promotions hotfix 1
assert_no_mutations

reset_scenario
existing='[{"number":42,"baseRefName":"Prod"}]'
run_case ignore-unrelated-pr release
assert_mutation 'pr create'

reset_scenario
branches='Hotfix-1.10.0'
run_case missing-normal-release release 1
assert_no_mutations

reset_scenario
branches='Release-1.10.0'
run_case missing-hotfix-release hotfix 1
assert_no_mutations

reset_scenario
run_case invalid-release-type unknown 1
assert_no_mutations
test ! -s "$promotion_scratch/calls"

reset_scenario
source_branch=feature/example
run_case reject-other-source-branch release 1
assert_no_mutations
test ! -s "$promotion_scratch/calls"

reset_scenario
ahead=0
run_case no-new-commits release
assert_no_mutations

reset_scenario
branch_failure=true
run_case github-read-failure release 17
assert_no_mutations

awk '
  /^        run: \|$/ && !found { reading=1; found=1; next }
  reading && /^  [^ ]/ { exit }
  reading {
    sub(/^          /, "")
    gsub(/\$\{\{ github.repository \}\}/, "ecillie/hockey-analytics")
    print
  }
' .github/workflows/release.yml > "$promotion_scratch/release-check.sh"
bash -n "$promotion_scratch/release-check.sh"

assert_release_check() {
  local target="$1" pr_title="$2" expected_status="$3" source="${4:-Dev}" status=0
  env PATH="$promotion_scratch:$PATH" GITHUB_EVENT_NAME=pull_request \
    TARGET_BRANCH="$target" SOURCE_BRANCH="$source" PR_TITLE="$pr_title" \
    TEST_BRANCHES="$branches" TEST_BRANCH_FAILURE=false TEST_CALLS="$promotion_scratch/calls" \
    bash "$promotion_scratch/release-check.sh" > "$promotion_scratch/output" 2>&1 || status=$?
  if [ "$status" -ne "$expected_status" ]; then
    cat "$promotion_scratch/output"
    echo "FAIL release check: $source -> $target ($pr_title)" >&2
    exit 1
  fi
  printf 'PASS release check: %s -> %s (%s)\n' "$source" "$target" "$pr_title"
}

reset_scenario
assert_release_check Release-1.10.0 'Promote Dev to Release-1.10.0' 0
assert_release_check Hotfix-1.10.0 'Hotfix: Promote Dev to Hotfix-1.10.0' 0
assert_release_check Release-1.10.0 'Hotfix: Promote Dev to Hotfix-1.10.0' 1
assert_release_check Hotfix-1.10.0 'Promote Dev to Release-1.10.0' 1
assert_release_check Release-1.9.0 'Promote Dev to Release-1.9.0' 1
assert_release_check Release-1.10.0 'Promote Dev to Release-1.10.0' 1 feature/example

#!/usr/bin/env bash
set -euo pipefail
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GITHUB_REF_NAME:?GITHUB_REF_NAME is required}"
: "${PROMOTION_TYPE:?PROMOTION_TYPE must be release or hotfix}"
if [ "$GITHUB_REF_NAME" != Dev ]; then
  echo "Promotion must run from Dev." >&2
  exit 1
fi
case "$PROMOTION_TYPE" in
  release) prefix=Release- ;;
  hotfix) prefix=Hotfix- ;;
  *) echo "PROMOTION_TYPE must be release or hotfix." >&2; exit 1 ;;
esac

target=$(gh api "repos/$GITHUB_REPOSITORY/branches" --paginate --jq '.[].name' \
  | awk -v prefix="$prefix" '$0 ~ ("^" prefix "[0-9]+[.][0-9]+[.][0-9]+$")' \
  | sort -V | tail -1)
if [ -z "$target" ]; then
  echo "Create a ${prefix}x.y.z branch before promoting Dev." >&2
  exit 1
fi

ahead=$(gh api "repos/$GITHUB_REPOSITORY/compare/$target...Dev" --jq '.ahead_by')
if [ "$ahead" -eq 0 ]; then
  echo "Dev has no commits to promote to $target."
  exit 0
fi

existing=$(gh pr list --repo "$GITHUB_REPOSITORY" --head Dev --state open \
  --json number,baseRefName \
  --jq '.[] | select(.baseRefName | test("^(Release|Hotfix)-[0-9]+\\.[0-9]+\\.[0-9]+$")) | [.number, .baseRefName] | @tsv')
count=$(printf '%s\n' "$existing" | awk 'NF { count++ } END { print count+0 }')
if [ "$count" -gt 1 ]; then
  echo "Multiple Dev promotion PRs are open; resolve them before choosing a destination." >&2
  exit 1
fi

title="Promote Dev to $target"
if [ "$PROMOTION_TYPE" = hotfix ]; then
  title="Hotfix: Promote Dev to $target"
fi
body="Promotion type: $PROMOTION_TYPE. Promote all pending Dev changes to $target. This PR merges after the destination branch requirements pass. Production promotion remains manual."

if [ "$count" -eq 0 ]; then
  gh pr create --repo "$GITHUB_REPOSITORY" --base "$target" --head Dev \
    --title "$title" --body "$body"
  exit 0
fi

read -r number current_base <<< "$existing"
current_title=$(gh pr view "$number" --repo "$GITHUB_REPOSITORY" --json title --jq '.title')
if [ "$current_base" = "$target" ] && [ "$current_title" = "$title" ]; then
  echo "Dev promotion PR #$number already targets $target."
  exit 0
fi

auto_merge=$(gh pr view "$number" --repo "$GITHUB_REPOSITORY" --json autoMergeRequest --jq '.autoMergeRequest != null')
if [ "$auto_merge" = true ]; then
  gh pr merge "$number" --repo "$GITHUB_REPOSITORY" --disable-auto
fi
gh pr edit "$number" --repo "$GITHUB_REPOSITORY" --base "$target" \
  --title "$title" --body "$body"
echo "Dev promotion PR #$number now targets $target; destination checks must pass."

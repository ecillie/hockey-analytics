# CI and Release Promotion

TradeValue uses four workflows:

- `Route pull request` sends every feature-branch PR to `Dev`, regardless of
  its title or initially selected base. Only `Dev` and versioned
  `Release-x.y.z` / `Hotfix-x.y.z` heads are treated as promotion branches.
  A feature PR titled `Hotfix: Fix cap calculation` still targets `Dev`.
  Existing release/hotfix promotion PRs into `Prod` retain that destination.
- `Dev` validates feature PRs and the integration branch. A successful push
  to `Dev`, including a merged feature PR, opens a promotion PR into the
  highest `Release-x.y.z` branch.
- `Release` validates and auto-merges pull requests into `Release-x.y.z` and
  `Hotfix-x.y.z` branches. Its required check also verifies that the PR title
  matches the branch type and that the base is the latest branch of that type.
  After a successful push with commits ahead of `Prod`, it opens or updates a
  promotion PR into `Prod`.
- `Prod` validates promotion PRs. A person reviews and merges them manually
  after `Prod required` and any other branch requirements pass.

## Release and patch branches

Every PR from a feature branch must target `Dev`. Start feature branches from
current `origin/Dev` and create their PRs with `gh pr create --base Dev`.
Feature branches do not target release, hotfix, or production branches directly.
This rule also applies to documentation, cleanup, remediation, and urgent-fix
feature branches; titles never override it.

Create the next ordinary release branch as `Release-x.y.z`, such as
`Release-1.1.0`. Use the latest deployed release or `Prod` as its starting
point, and include any intended work still present only on `Dev`. The highest
versioned release branch receives promotion PRs from `Dev`, so create a higher
branch only when it should become the active promotion destination. Numeric
sorting means
`Release-1.10.0` follows `Release-1.9.0`.
Dev pushes target the same highest release branch. An older Dev promotion PR
cannot pass the release check once a newer branch becomes active.

For an urgent fix to the version already in production, branch from `Prod` as
`Hotfix-x.y.z`, where `x.y.z` is the next patch version of the production line.
For example, while `1.1.0` is the active release and `1.0.0` is in production,
name the dedicated patch branch `Hotfix-1.0.1`. Dedicated hotfix branches are
release-management branches; a feature branch for an urgent fix still opens
its PR into `Dev`. A `Hotfix` title does not route a feature PR to a hotfix
branch. The dedicated hotfix branch's push opens a
`Hotfix-1.0.1 → Prod` promotion PR for manual merge. Any feature work carrying
the fix forward must also target `Dev` so the normal release promotion retains it.

Create the hotfix branch from `Prod` only after this workflow has reached
`Prod`; otherwise a branch made from an older `Prod` commit will not contain
the `Release` workflow and cannot run its PR checks. The initial hotfix branch
push has no commits ahead of `Prod`, so it creates no promotion PR.

The Dev, Release, and Prod workflows call `_reusable-ci.yml`, so backend tests,
ML tests, frontend lint, frontend tests, and the frontend production build use
the same implementation.
On Dev and release pull requests, CI selects jobs by changed paths:
`frontend/**` runs the frontend job, `backend/**` runs the backend job, and
`ml/**` runs the ML job. Shared configuration, OpenAPI contract, and workflow
changes run every affected job. Prod pull requests and pushes to Dev, release,
hotfix, and Prod branches run all three jobs. Each selected job runs its full
local suite because coverage thresholds apply to the whole area.
Frontend promotion requires 100% statement, branch, function, and line coverage
for production runtime modules. CI publishes the HTML, JSON, LCOV, and Cobertura
reports in the `frontend-coverage` artifact for release review and auditability.
The backend job also verifies a linear Alembic history, upgrades an empty local
PostgreSQL service, compares its catalog with the committed schema snapshot,
tests a downgrade/re-upgrade cycle, runs API smoke checks, and uploads offline
SQL plus catalog diagnostics.
The Release workflow enables auto-merge only after its required check succeeds.
GitHub then waits on every other check required by the release branch, including
Vercel preview checks when configured. The Dev and Release push jobs create
promotion PRs; the Prod workflow never enables auto-merge.

## Frontend release gate

The frontend coverage thresholds live in `frontend/vite.config.ts` and must stay
at 100% for statements, branches, functions, and lines. The measured scope
includes application routing, API selection and transport, shared components,
hooks, context, page behavior, formatting, error handling, and user
interactions.

The coverage denominator excludes only files that do not represent shipped
runtime behavior: TypeScript-only declarations, the DOM bootstrap, test setup,
and mock fixtures/services. The mock API remains directly covered by contract
tests even though it is excluded from the production-runtime percentage.

For every promotion candidate, confirm that:

1. `Frontend tests and build` passes without lowering a threshold or adding a
   production module to the exclusion list.
2. The `frontend-coverage` artifact contains `index.html`,
   `coverage-final.json`, `lcov.info`, and `cobertura-coverage.xml`.
3. `npm run build` succeeds after the coverage gate, proving the tested source
   also compiles into the production artifact.
4. Any intentional behavior change includes interaction coverage for its
   success, loading, empty, failure, and retry states where applicable.

## Repository settings

### Pull request settings

Open **Settings → General → Pull Requests**:

1. Enable **Allow merge commits**.
2. Enable **Allow auto-merge**.

Auto-merge applies to Dev and release branches only. Prod PRs require a manual
merge after all requirements pass.
See [GitHub's auto-merge documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-auto-merge-for-pull-requests-in-your-repository).

### Actions secret

Open **Settings → Secrets and variables → Actions**:

1. Confirm that the repository secret `PROMOTION_TOKEN` exists. Its token must
   be scoped to this repository and have **Contents: Read and write** and
   **Pull requests: Read and write** permissions. Also grant **Workflows: Read
   and write** if automated promotions must merge pull requests that modify
   files under `.github/workflows/`.

The router and promotion jobs use `PROMOTION_TOKEN` rather than `GITHUB_TOKEN`
so their PR edits and creations trigger the next GitHub Actions workflow. The
router uses `pull_request_target` from the default branch and never checks out
or executes PR code. Keep the default workflow permission at **Read repository
contents and packages**.

### Branch rulesets

Open **Settings → Rules → Rulesets** and create three separate active branch
rulesets. A single ruleset cannot be used because each destination branch has a
different required check. The Release ruleset targets both versioned release
branches and `Hotfix-` branches.

Configure each ruleset as follows:

- Enforcement status: **Active**
- Bypass list: empty
- Target: use the pattern in the table below
- Enable **Restrict deletions**
- Enable **Require a pull request before merging**
- Required approvals: `0`
- Enable **Require status checks to pass before merging**
- Disable **Require branches to be up to date before merging**
- Keep force pushes blocked
- Do not enable **Restrict updates**
- Do not require deployments at this stage

Add only the check matching the target branch:

| Ruleset target | Required check |
| --- | --- |
| `Dev` | `Dev required` |
| `Release-*.*.*` and `Hotfix-*.*.*` | `Release required` |
| `Prod` | `Prod required` |

GitHub ruleset patterns are globs, not strict version validators. The Release
workflow also checks the exact branch format before its required check passes.

Strict up-to-date mode is intentionally disabled. A downstream merge adds a
merge commit absent from the upstream branch. The workflows run the destination
checks on each PR; Prod still requires a manual merge.

GitHub explains these options in its
[ruleset documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository)
and [required-status-check documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#require-status-checks-to-pass-before-merging).

## Safe rollout

1. Temporarily turn off repository auto-merge before updating `Prod`; its old
   workflow still enables auto-merge until the replacement reaches that branch.
   Merge these workflow changes into `Dev`, promote them to the current
   `Release-x.y.z` branch, and configure its ruleset. Manually merge the
   workflow update into the default branch (`Prod`) after `Prod required`
   passes, then turn repository auto-merge back on for release PRs. Disable
   auto-merge on any already open Prod PRs and retire the old `NonProd` ruleset
   after its open PRs are handled. The router starts working once it is on
   `Prod`.
2. Open a feature PR into `Dev`. Confirm the router keeps `Dev` even if the
   title contains `Hotfix` or the PR initially targets a release branch.
   Confirm `Dev required` succeeds before automatic merge into `Dev`.
3. Confirm `Dev` opens a promotion PR into the highest `Release-x.y.z` branch
   and `Release required` succeeds. Then confirm the release branch opens a
   PR into `Prod`, `Prod required` succeeds, and a person merges it manually.
4. Create a dedicated hotfix branch from `Prod`. Confirm its promotion PR
   into `Prod` retains that base and waits for manual merge. Every feature
   branch used for related work must still target `Dev`.

If a required job fails or is cancelled, the destination pull request remains
open. Rerun the failed jobs or push a corrective commit. Prod promotion remains
manual even after its checks pass.

Validate the routing rules locally with `bash scripts/test-pr-routing.sh`.
The checks use a fake GitHub CLI and do not change real PRs. They cover feature
targets and titles, an absent release branch, Dev promotion version selection,
and release/hotfix promotions into Prod. The router runs from the repository's
default branch through `pull_request_target`; a router change takes effect
after the normal promotion process delivers it to `Prod`.

## Database migration release gate

Database changes are deliberately separate from Vercel application startup and
the automatic branch cascade. Create GitHub Environments named `nonprod` and
`prod`, add a direct Neon connection as the `DATABASE_URL` secret in each, and
configure required reviewers on `prod`.

Before releasing schema-dependent code, manually dispatch the `Database
migration` workflow against `nonprod` on the current `Release-x.y.z` branch (or
the `Hotfix-x.y.z` branch for a patch),
validate the application, and then
dispatch it against `prod`. Per-environment concurrency prevents overlapping
migration runs. The workflow records the starting and ending revision, applies
`upgrade head`, verifies the exact schema contract, and smoke-tests health,
seasons, and teams. Use pooled URLs only for the request-serving application;
the migration workflow requires a direct Neon URL.

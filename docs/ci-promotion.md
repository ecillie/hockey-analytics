# CI and Release Promotion

TradeValue uses three environment workflows:

- `Dev` validates and squash-merges pull requests into `Dev`. After the
  resulting successful push, it finds the newest
  `Release-MAJOR.MINOR.PATCH` branch and opens or updates the promotion pull
  request to it.
- `Release` validates and merge-commits pull requests into the newest release
  branch. After the resulting successful push, it opens or updates that
  release branch's promotion pull request to `Prod`.
- `Prod` validates pull requests into `Prod`. A person must merge the pull
  request with a merge commit after every required check passes.

Release precedence is numeric from left to right: major, then minor, then
patch. For example, `Release-10.1.0` is newer than `Release-9.99.99`, and
`Release-10.2.0` is newer than `Release-10.1.99`. Names that do not exactly
match `Release-MAJOR.MINOR.PATCH`, such as `Release-MVP`, are ignored. The
promotion fails clearly when no matching release branch exists.

All three call `_reusable-ci.yml`, so backend tests, ML tests, frontend lint,
frontend tests, and the frontend production build use the same implementation.
Frontend promotion requires 100% statement, branch, function, and line coverage
for production runtime modules. CI publishes the HTML, JSON, LCOV, and Cobertura
reports in the `frontend-coverage` artifact for release review and auditability.
The backend job also verifies a linear Alembic history, upgrades an empty local
PostgreSQL service, compares its catalog with the committed schema snapshot,
tests a downgrade/re-upgrade cycle, runs API smoke checks, and uploads offline
SQL plus catalog diagnostics.
The Dev and Release workflows own their destination merges. Their merge jobs
run only after the required aggregate job succeeds. GitHub auto-merge remains
responsible for waiting on every other check required by the destination
branch, including Vercel preview checks when those are configured as required.
The push jobs only create the next promotion pull request; they do not merge it
themselves. The Prod workflow never enables auto-merge.

Promotion pull requests use consistent, searchable titles:

- `release: promote Dev → Release-1.2.0`
- `release: promote Release-1.2.0 → Prod`

Feature pull requests should use concise conventional titles such as
`feat(players): add contract history` or
`fix(ci): select the latest release numerically`.

## Merge strategy

| Pull request | Merge method | Enforcement |
| --- | --- | --- |
| Feature branch → `Dev` | Squash merge | Automated by `dev.yml` |
| `Dev` → `Release-MAJOR.MINOR.PATCH` | Merge commit | Automated by `release.yml` |
| `Release-MAJOR.MINOR.PATCH` → `Prod` | Merge commit | Manual after `Prod required` passes |

Squashing feature work keeps development history concise. Promotion pull
requests retain merge commits so the long-lived branches preserve ancestry;
squashing a promotion can make later comparisons and merges repeat or conflict
with commits that Git no longer recognizes as shared history.

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
2. Enable **Allow squash merging**.
3. Enable **Allow auto-merge** for Dev and release-branch promotion.

Auto-merge waits until all requirements on the destination branch have passed.
See [GitHub's auto-merge documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-auto-merge-for-pull-requests-in-your-repository).

### Actions secret

Open **Settings → Secrets and variables → Actions**:

1. Confirm that the repository secret `PROMOTION_TOKEN` exists. Its token must
   be scoped to this repository and have **Contents: Read and write** and
   **Pull requests: Read and write** permissions. Also grant **Workflows: Read
   and write** if automated promotions must merge pull requests that modify
   files under `.github/workflows/`.

The workflows use `PROMOTION_TOKEN` rather than `GITHUB_TOKEN` so pull requests
and merges created by the promotion job trigger the next GitHub Actions
workflow. Keep the default workflow permission at **Read repository contents
and packages**; the workflow does not need a broadly writable `GITHUB_TOKEN`.

### Branch rulesets

Open **Settings → Rules → Rulesets** and create three separate active branch
rulesets. A single ruleset cannot be used because each destination branch type
has a different required check.

Configure each ruleset as follows:

- Enforcement status: **Active**
- Bypass list: empty
- Target: include the branch name or release-branch pattern shown below
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
| `Release-*.*.*` | `Release required` |
| `Prod` | `Prod required` |

Strict up-to-date mode is intentionally disabled. Each downstream merge adds a
merge commit that is not present on the upstream environment branch. Requiring
the promotion branch to contain that downstream merge commit would stop the
next unattended promotion. The workflows instead serialize promotions and run
the complete destination check on every promotion pull request.

GitHub explains these options in its
[ruleset documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository)
and [required-status-check documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#require-status-checks-to-pass-before-merging).

## Safe rollout

1. Open or update a pull request into `Dev`. Confirm `Dev required` succeeds
   and the workflow enables squash auto-merge for the pull request.
2. Confirm GitHub selects the numerically newest release branch, creates the
   `Dev → Release-MAJOR.MINOR.PATCH` pull request, and enables auto-merge.
   Confirm `Release required` appears and succeeds.
3. Confirm GitHub merges that pull request into the release branch and creates
   the `Release-MAJOR.MINOR.PATCH → Prod` pull request. Confirm `Prod required`
   appears and succeeds.
4. Review and manually merge the final pull request into `Prod` with **Create a
   merge commit**. Do not squash the promotion pull request.

If a required job fails or is cancelled, the destination pull request remains
open. Rerun the failed jobs or push a corrective commit. Auto-merge resumes for
Dev and release pull requests only; Prod always requires a manual merge.

## Database migration release gate

Database changes are deliberately separate from Vercel application startup and
branch promotion. Create GitHub Environments named `nonprod` and
`prod`, add a direct Neon connection as the `DATABASE_URL` secret in each, and
configure required reviewers on `prod`. `nonprod` remains the runtime and
database environment name; it is no longer a Git branch.

Before releasing schema-dependent code, select the newest release branch and
manually dispatch the `Database migration` workflow against `nonprod`, validate
the application, and then select `Prod` and dispatch it against `prod`. The
workflow verifies these branch choices using the same release selection logic.
Per-environment concurrency prevents overlapping migration runs. The workflow
records the starting and ending revision, applies `upgrade head`, verifies the
exact schema contract, and smoke-tests health, seasons, and teams. Use pooled
URLs only for the request-serving application; the migration workflow requires
a direct Neon URL.

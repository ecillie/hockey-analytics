# Repository instructions

## Feature branches and pull requests

- Every pull request from a feature branch must target `Dev`.
- Start feature branches from current `origin/Dev`. Include required preceding
  work through `Dev` before starting a dependent feature.
- Use `--base Dev` when creating a feature PR with `gh pr create`.
- PR titles, including titles containing `Hotfix`, do not change this rule.
- `Dev` promotes to the current `Release-x.y.z` branch through the release
  workflow. Release and dedicated hotfix branches promote to `Prod` for manual
  approval. These promotion PRs are distinct from feature PRs.
- Follow this rule if older plans or historical verification records describe
  feature PRs targeting release branches.

See [CI and release promotion](docs/ci-promotion.md) for the complete workflow.

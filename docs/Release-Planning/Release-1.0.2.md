# Release 1.0.2: Azure migration plan

## Goal

Move TradeValue from Vercel and Neon to Azure in one release, using only
resources that are always free or free for 12 months. The release covers:

- Setting up nonprod and prod cloud environments with Terraform.
- Moving the frontend, API, database, ingestion, logging, and existing data
  files to Azure.
- Deleting Vercel and Neon.

The app should run like a production app: real monitoring, browser telemetry,
and alerts, not just a hosted demo.

Free-tier limits change. Confirm the numbers here on Azure's free services page
before relying on them.

## Decisions

| Topic | Decision |
|---|---|
| Subscription | Azure free account, so the 12-month offers apply. |
| Scope | One release: build, cut over, and delete Vercel and Neon. |
| Region | East US for every resource except the Postgres server, which is in Central US: Azure offers this subscription no Postgres Flexible Server versions in East US (decided 2026-11-12). |
| Infrastructure | Terraform, so a later move to GCP, Oracle, or AWS stays possible. |
| Database | Postgres Flexible Server B1ms. One server holds a `nonprod` and a `prod` database, each with its own login. |
| Database after year one | Stay on Postgres. Set a reminder 11 months after the server is created. |
| Shared resource group | `hockey-analytics-shared` holds the Postgres server and the Terraform state. |
| API idle behaviour | Scale to zero; a cold start after idle is acceptable. |
| Ingestion schedule | Manual in both environments. Scheduled updates come in the next release. |
| Container images | Public images on GitHub Container Registry (ghcr.io). |
| Secrets | One Key Vault per environment. Container Apps read it through a managed identity. |
| GitHub to Azure access | OIDC, with a separate Azure identity for each GitHub Environment (`nonprod`, `prod`). Each identity can change only its own resource group. `prod` requires your approval. |
| Domain | None. Use the default Azure URLs. |
| Log retention and cap | 31 days, the free amount and also the minimum. Daily cap of 0.1 GB for prod and 0.05 GB for nonprod. |
| Browser telemetry | Application Insights browser SDK with cookies off. No consent banner needed. |
| Pull request previews | On for the nonprod Static Web App, pointed at the nonprod API. |
| Blob storage | Move the season CSVs and ML artifacts into blob storage. |
| Neon and Vercel | Delete as soon as prod runs on Azure. No soak period and no Neon backup. There are no users yet. |

## Resource layout

| Resource group | Contents |
|---|---|
| `hockey-analytics-shared` | Postgres Flexible Server (B1ms) with the `nonprod` and `prod` databases. Storage account for Terraform state, private, with blob versioning on. |
| `hockey-analytics-nonprod` | Static Web App (Free), Container Apps environment with the API app and the ingestion job, storage account, Log Analytics workspace and Application Insights, Key Vault, managed identity, alerts. |
| `hockey-analytics-prod` | Same set as nonprod. |

Subscription-wide: a $1 Cost Management budget with email alerts, and the
two GitHub OIDC identities in Microsoft Entra ID.

| Need | Resource | Free terms |
|---|---|---|
| Frontend | Static Web Apps, Free plan | Always free; free SSL; up to 3 preview environments |
| API and ingestion job | Container Apps (consumption) | Always-free monthly grant: about 180k vCPU-seconds, 360k GiB-seconds, 2M requests |
| Database | Postgres Flexible Server, B1ms | Free for 12 months: 750 hours, 32 GB storage, 32 GB backup |
| Logging | Log Analytics and Application Insights | First 5 GB a month free across the billing account |
| Blob storage | Storage account, hot LRS | 5 GB free for 12 months |
| Secrets | Key Vault, Standard | About $0.03 per 10,000 reads |
| Images | ghcr.io, public | Free |

Default URLs, one set per environment:

- Frontend: `https://<generated-name>.azurestaticapps.net`
- API: `https://<app-name>.<generated-id>.eastus.azurecontainerapps.io`

These go into `CORS_ORIGINS` on the API and `VITE_API_BASE_URL` in the
frontend build.

## Work breakdown

Each item below is one or more feature branches into `Dev`, in this order.

1. **Terraform bootstrap.** A small one-time configuration creates
   `hockey-analytics-shared`, the Terraform state storage account, the two OIDC
   identities with federated credentials for the `nonprod` and `prod` GitHub
   Environments, and the cost budget. It runs once from a local machine;
   everything later runs from GitHub Actions, except `envs/shared`, which the
   operator applies from a local machine. Terraform isn't installed locally
   yet.
2. **Terraform: shared and environment modules.** Code lives under `infra/`.
   - The shared module creates the Postgres server, both databases, and their
     logins.
   - One environment module, used for both nonprod and prod, creates the Static
     Web App, Container Apps environment, API app, ingestion job, storage
     account, Log Analytics workspace with its cap, Application Insights, Key
     Vault, managed identity, and alerts (API 5xx, ingestion job failure).
3. **Infrastructure workflow.** GitHub Actions runs `terraform plan` and
   `apply` per environment through OIDC. Prod waits for your approval.
4. **API container deploy.** CI builds the existing `backend/Dockerfile` and
   pushes a public image to ghcr.io. A deploy workflow updates the Container
   App, which uses `/api/health` as its health check. Secrets come from Key
   Vault.
5. **API telemetry.** Send the existing structured logs, request traces, and
   exceptions to Application Insights through OpenTelemetry. The connection
   string comes from Key Vault. The events defined in `docs/logging-events.md`
   stay the same.
6. **Ingestion job.** Before `run_all`, the job downloads the season CSVs from
   blob storage into a local folder and points `TRADEVALUE_DATA_DIR` at it. The
   job reads blob storage through its managed identity and runs only when
   triggered manually.
7. **Frontend deploy.** A Static Web Apps workflow builds with the environment's
   `VITE_API_BASE_URL`, with pull request previews on nonprod. Add the
   Application Insights browser SDK with cookies off, following the privacy
   rules in `docs/logging-events.md`.
8. **Database migration workflow.** Point `database-migrate.yml` at Azure
   Postgres: its `DATABASE_URL` secrets in the GitHub `nonprod` and `prod`
   Environments, `sslmode=require`, and the server's firewall must allow the
   GitHub runner. Update the workflow's Neon-specific wording and connection
   checks.
9. **Data upload.** Upload `backend/data` and the ML artifacts
   (`ml/models/*.joblib`, `ml/evaluation/outputs`) to blob containers in each
   environment's storage account.
10. **Remove Vercel files and update docs.** Delete `backend/index.py`,
    `backend/vercel.json`, and `frontend/vercel.json`. Replace
    `docs/deployment-vercel-neon.md` with an Azure deployment guide, and update
    `docs/ci-promotion.md` where it mentions Vercel.

## Cutover

1. Apply the nonprod infrastructure, run the nonprod migration, upload the data,
   run ingestion, and smoke-test the nonprod frontend and API.
2. Promote to prod. Apply the prod infrastructure, run the prod migration
   (approval required), upload the data, run ingestion, and smoke-test.
3. Delete both Vercel projects and the Neon project. Remove Neon and Vercel
   secrets and variables from GitHub.

## Risks

| Risk | Handling |
|---|---|
| No Neon backup. The Azure databases are rebuilt from scratch by ingestion, so contract data is scraped again from capwages.com and Neon's ingestion history is lost. | Accepted: there are no users. Check row counts against Neon before deleting it. |
| Postgres free year ends around November 2027. | Calendar reminder; decide then whether to pay about $12–15 a month or move. |
| Terraform state contains database passwords. | Private storage account, versioning on. The shared state, which holds the Postgres admin and login passwords, is readable only by the operator who ran bootstrap. Each environment's state is also readable by its own deploy identity. |
| A public image could leak secrets if one is baked in. | The Dockerfile copies only `src`, `requirements.txt`, `pyproject.toml`, and `database`. Secrets are supplied at runtime from Key Vault. |
| Logging could exceed the free 5 GB. | Daily caps per workspace, plus the cost budget alert. |
| Postgres firewall too open, or blocks GitHub runners. | Decide the access rule while building item 8. |

## Open items

- **Ingestion run time.** How long does a full `run_all` take today? It sets the
  Container Apps Job timeout. A guess is fine; it can be measured on the first
  nonprod run.

  like 10 minutes?

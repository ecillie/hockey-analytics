# Infrastructure

Terraform for the Azure deployment described in
[Release 1.0.2](../docs/Release-Planning/Release-1.0.2.md). Everything runs in
East US except the shared Postgres server, which is in Central US because Azure
offers this subscription no Postgres Flexible Server versions in East US.

| Directory | Purpose | Runs from |
|---|---|---|
| `bootstrap/` | One-time setup: resource groups, Terraform state storage, GitHub OIDC identities, cost budget. | A local machine, once. |
| `modules/environment/` | Module for one environment: Key Vault, storage, observability, identity, Container App, Static Web App, alerts. | Called by `envs/nonprod` and `envs/prod`. |
| `modules/shared/` | Module for the shared Postgres server, per-environment databases and roles, and the `database-url` Key Vault secrets. | Called by `envs/shared`. |
| `envs/nonprod/` | Root for the nonprod environment (state container `tfstate-nonprod`). | GitHub Actions (see [Infrastructure workflow](#infrastructure-workflow)) or a local machine. |
| `envs/prod/` | Root for the prod environment (state container `tfstate-prod`). | GitHub Actions or a local machine. |
| `envs/shared/` | Root for the shared Postgres server (state key `shared.tfstate` in container `tfstate`). | A local machine only. |

## Bootstrap

Bootstrap creates:

- Resource groups `hockey-analytics-shared`, `hockey-analytics-nonprod`, and
  `hockey-analytics-prod`.
- A private storage account in the shared group with versioning and 30-day soft
  delete, holding three containers: `tfstate` (bootstrap), `tfstate-nonprod`,
  and `tfstate-prod`.
- Two user-assigned identities, `hockey-analytics-github-nonprod` and
  `hockey-analytics-github-prod`, each federated with one GitHub Environment of
  `ecillie/hockey-analytics` and with its pull request runs, which plan without
  an Environment. The subjects use the repository's immutable OIDC form,
  `repo:ecillie@157654232/hockey-analytics@1105536195:...`. Each identity gets Contributor and Role Based
  Access Control Administrator on its own resource group and Storage Blob Data
  Contributor on its own state container.
- A monthly subscription budget (default $1) that emails at 50% and 100% of
  actual spend and 100% of forecast spend.

### Prerequisites

- Terraform `~> 1.17.1` and the Azure CLI.
- An account with Owner (or Contributor plus User Access Administrator) on the
  subscription, since bootstrap creates role assignments.

### First run

```sh
az login
cd infra/bootstrap

cat > terraform.tfvars <<'EOF'
subscription_id            = "<subscription-guid>"
state_storage_account_name = "<globally-unique, 3-24 lowercase letters/digits>"
budget_contact_emails      = ["you@example.com"]
EOF

terraform init
terraform plan -out bootstrap.tfplan
terraform apply bootstrap.tfplan
```

`terraform.tfvars` is not committed; it holds the subscription ID and email.

Bootstrap has already been applied and its state lives in
`hockeyanalyticstfstate/tfstate/bootstrap.tfstate` (see `backend.tf`). To make
changes later, run `az login`, recreate `terraform.tfvars`, then
`terraform init` and `terraform plan` as usual.

The provider registers every Azure resource provider 1.0.2 needs, because the
GitHub identities are scoped to their resource groups and cannot register
providers themselves. Add new namespaces to `providers.tf` here.

Bootstrap also grants the operator Storage Blob Data Contributor on
`tfstate-nonprod` and `tfstate-prod`, so the environment roots can be planned
locally.

### Rebuilding from scratch

`backend.tf` points at a storage account this configuration creates, so a
first run on a fresh subscription must start with local state:

1. Move `backend.tf` aside and run the first-run commands above.
2. Restore `backend.tf` and run `terraform init -migrate-state`. Role
   assignments can take a few minutes, so retry if it returns a 403.
3. Delete the local `terraform.tfstate` and `terraform.tfstate.backup`.

Resource groups that already exist must be imported first, for example
`terraform import azurerm_resource_group.shared /subscriptions/<id>/resourceGroups/hockey-analytics-shared`.

### Configure GitHub

The `nonprod` and `prod` GitHub Environments exist, with your approval required
on `prod`. Their names must stay lowercase: the federated credentials match the
OIDC subject exactly.

The Infrastructure workflow reads repository-level settings, because pull
request plans run outside any Environment. Take the IDs from
`terraform output`:

| Setting | Kind | Value |
|---|---|---|
| `AZURE_TENANT_ID` | variable | `azure_tenant_id` |
| `AZURE_SUBSCRIPTION_ID` | variable | `azure_subscription_id` |
| `AZURE_CLIENT_ID_NONPROD` | variable | `github_nonprod_client_id` |
| `AZURE_CLIENT_ID_PROD` | variable | `github_prod_client_id` |
| `TF_OPERATOR_PRINCIPAL_ID` | variable | `operator_principal_id` for both environment roots |
| `DATABASE_SECRET_READY_NONPROD`, `DATABASE_SECRET_READY_PROD` | variable | `database_secret_ready` per root; unset means `false` |
| `TF_ALERT_EMAIL_ADDRESSES` | secret | `alert_email_addresses` as a JSON list, for example `["you@example.com"]` |

The Environments also hold `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and
`AZURE_SUBSCRIPTION_ID` secrets for workflows that run inside an Environment.

Environment configurations use the same storage account with
`container_name` set to `nonprod_state_container_name` or
`prod_state_container_name`.

## Infrastructure workflow

`.github/workflows/infrastructure.yml` runs when `infra/` or the workflow
changes. It logs in to Azure through OIDC; no Azure credential is stored in
GitHub.

| Trigger | What runs |
|---|---|
| Pull request | `terraform plan` for `envs/nonprod` and `envs/prod`, shown in the run summary. Plans skip the state lock. |
| Push to `Release-x.y.z` or `Hotfix-x.y.z` | Plan and apply `envs/nonprod` in the `nonprod` Environment. |
| Push to `Prod` | Plan and apply `envs/prod` after approval in the `prod` Environment. Review the prod plan on the promotion pull request before approving. |
| Manual run | The same as a push to the selected branch. |

`envs/shared` and `bootstrap/` stay local.

## Environments and shared Postgres

Each root under `envs/` keeps its own state in the bootstrap storage account
and reads a gitignored `terraform.tfvars`. Create it before `terraform init`.

| Root | `terraform.tfvars` inputs |
|---|---|
| `envs/nonprod`, `envs/prod` | `subscription_id` (optional if `ARM_SUBSCRIPTION_ID` is set), `operator_principal_id` (object ID granted Key Vault Secrets Officer), `alert_email_addresses` (optional, sensitive), `database_secret_ready` (default `false`). |
| `envs/shared` | `subscription_id` (optional if `ARM_SUBSCRIPTION_ID` is set), `operator_ip` (your public IPv4, for example from `curl -s https://api.ipify.org`). |

`envs/shared` is applied locally, never from CI. It needs a reachable Postgres
server for the `postgresql` provider. Its firewall admits `operator_ip` and,
through Azure's `0.0.0.0` "allow Azure services" rule, the Container Apps, which
have no fixed outbound IP. Logins still need TLS and a per-environment
password. It writes the `database-url` secret into
`hockey-analytics-np-kv` and `hockey-analytics-prd-kv`, so those vaults must
exist first.

### Apply order

1. Apply `envs/nonprod` and `envs/prod` with `database_secret_ready = false`.
   This creates the Key Vaults without the resources that need the secret.
2. Apply `envs/shared` from a local machine. It creates the server, databases
   and roles, and writes `database-url` into each vault.
3. Apply `envs/nonprod` and `envs/prod` again with
   `database_secret_ready = true`. In GitHub Actions, set
   `DATABASE_SECRET_READY_NONPROD` or `DATABASE_SECRET_READY_PROD` to `true`
   and rerun the workflow on the branch for that environment.

```sh
cd infra/envs/<root>
terraform init
terraform plan -out <root>.tfplan
terraform apply <root>.tfplan
```

Before prod's first apply creates `hockey-analytics-prd-kv`, apply
`envs/shared` for nonprod only:

```sh
cd infra/envs/shared
terraform plan -out shared.tfplan \
  -target='module.shared.azurerm_key_vault_secret.database_url["nonprod"]' \
  -target='module.shared.postgresql_grant.connect["nonprod"]' \
  -target='module.shared.postgresql_grant.public_connect_revoke["nonprod"]' \
  -target='module.shared.postgresql_grant.schema["nonprod"]' \
  -target='module.shared.azurerm_postgresql_flexible_server_firewall_rule.azure_services'
terraform apply shared.tfplan
```

Run a full `envs/shared` apply after the prod vault exists.

## API deploy workflow

`.github/workflows/api-deploy.yml` runs when `backend/` or the workflow changes
on a `Release-x.y.z`, `Hotfix-x.y.z`, or `Prod` push, or when run manually.

1. It builds `backend/Dockerfile` and `backend/ingestion.Dockerfile`, fails if
   either image contains a `.env` file, and pushes
   `ghcr.io/ecillie/hockey-analytics-api:<commit SHA>` and
   `ghcr.io/ecillie/hockey-analytics-ingestion:<commit SHA>`.
2. It logs in through OIDC and points the environment's Container App and
   ingestion job at those images: nonprod from a release or hotfix branch, prod
   from `Prod` after approval in the `prod` Environment. The job's image changes
   but the job does not run.
3. It smoke-tests `/api/health` and `/api/seasons` on the app's URL.

Deploys share a concurrency group with Terraform applies for the same
environment, so they never run at the same time. Terraform ignores the image,
so an apply does not roll a deploy back.

The Container App and job pull their images without registry credentials, so
both packages must be public. ghcr.io creates each as private on its first push;
set each to Public once under the package's **Package settings → Danger Zone →
Change visibility**.

The API needs `DATABASE_URL`, so deploy only after `envs/shared` has written
`database-url` and the environment has been applied with
`database_secret_ready = true`.

## Data upload

`scripts/upload-blob-data.sh <nonprod|prod>` uploads the local data files to the
environment's storage account. Your az login needs Storage Blob Data
Contributor there; Terraform grants it to `operator_principal_id`.

| Container | Contents |
|---|---|
| `ingestion-data` | `backend/data/**/*.csv`, keeping its folders, for example `skater advanced/skaters_2008_to_2024.csv` |
| `ml-artifacts` | `models/*.joblib` from `ml/models`, and `evaluation/outputs/*` from `ml/evaluation/outputs` |

The joblib model is gitignored, so it must exist locally first. Rerunning the
script overwrites blobs in place and doesn't delete blobs missing locally.

## Ingestion job

The ingestion job runs only when started by hand:

```bash
az containerapp job start \
  --name hockey-analytics-<env>-ingest \
  --resource-group hockey-analytics-<env>
```

Each run downloads every blob in the environment's private `ingestion-data`
container (the `backend/data` layout, for example
`skater advanced/skaters_2008_to_2024.csv`) into a temporary folder, sets
`TRADEVALUE_DATA_DIR` to it, and runs `run_all`. It reads storage as the
environment's managed identity (`AZURE_CLIENT_ID`), which holds Storage Blob
Data Reader; the account has shared keys disabled. `terraform output
ingestion_data_container_url` gives the container URL.

A run that exits nonzero, including a failed download or an empty container,
fails the execution and fires the ingestion failure alert. The replica timeout
is `ingestion_timeout_seconds` (30 minutes by default); adjust it after timing
the first nonprod run.

## Frontend deploy workflow

`.github/workflows/frontend-deploy.yml` deploys `frontend/` to the environment's
Static Web App. `scripts/frontend-deploy-settings.sh` reads the settings each
build needs from Azure: the API URL, the Static Web App host and deploy token,
and the Application Insights connection string. No GitHub secret holds them.

- A `Release-x.y.z` or `Hotfix-x.y.z` push deploys nonprod. A `Prod` push
  deploys prod after approval in the `prod` Environment. Each build sets `ENV`,
  `VITE_API_BASE_URL`, `VITE_USE_MOCK_API=false` and
  `VITE_APPINSIGHTS_CONNECTION_STRING`, then the workflow checks that `/`,
  `/players` and `/players/1` serve the app.
- A pull request into `Dev` that changes the frontend gets a preview on the
  nonprod Static Web App, built against the nonprod API, and the action
  comments its URL on the pull request. Closing the pull request removes the
  preview. The Free plan allows three previews at a time. Pull requests from
  forks are skipped because they get no OIDC token.
- With previews on, the nonprod API also sets `CORS_ORIGIN_REGEX` to accept
  only this app's preview hosts (`<subdomain>-<number>.<region>…azurestaticapps.net`).

`frontend/public/staticwebapp.config.json` rewrites client routes such as
`/players/1` to `index.html`.


# Infrastructure

Terraform for the Azure deployment described in
[Release 1.0.2](../docs/Release-Planning/Release-1.0.2.md). Everything runs in
East US.

| Directory | Purpose | Runs from |
|---|---|---|
| `bootstrap/` | One-time setup: resource groups, Terraform state storage, GitHub OIDC identities, cost budget. | A local machine, once. |

## Bootstrap

Bootstrap creates:

- Resource groups `hockey-analytics-shared`, `hockey-analytics-nonprod`, and
  `hockey-analytics-prod`.
- A private storage account in the shared group with versioning and 30-day soft
  delete, holding three containers: `tfstate` (bootstrap), `tfstate-nonprod`,
  and `tfstate-prod`.
- Two user-assigned identities, `hockey-analytics-github-nonprod` and
  `hockey-analytics-github-prod`, each federated with one GitHub Environment of
  `ecillie/hockey-analytics`. Each identity gets Contributor and Role Based
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
OIDC subject exactly. Each Environment holds these secrets, taken from the
outputs:

```sh
terraform output
```

| Secret | `nonprod` | `prod` |
|---|---|---|
| `AZURE_CLIENT_ID` | `github_nonprod_client_id` | `github_prod_client_id` |
| `AZURE_TENANT_ID` | `azure_tenant_id` | `azure_tenant_id` |
| `AZURE_SUBSCRIPTION_ID` | `azure_subscription_id` | `azure_subscription_id` |

Environment configurations use the same storage account with
`container_name` set to `nonprod_state_container_name` or
`prod_state_container_name`.

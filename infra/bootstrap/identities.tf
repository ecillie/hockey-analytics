resource "azurerm_user_assigned_identity" "github_nonprod" {
  name                = "hockey-analytics-github-nonprod"
  resource_group_name = azurerm_resource_group.shared.name
  location            = azurerm_resource_group.shared.location
}

resource "azurerm_user_assigned_identity" "github_prod" {
  name                = "hockey-analytics-github-prod"
  resource_group_name = azurerm_resource_group.shared.name
  location            = azurerm_resource_group.shared.location
}

resource "azurerm_federated_identity_credential" "github_nonprod" {
  name                      = "github-nonprod"
  user_assigned_identity_id = azurerm_user_assigned_identity.github_nonprod.id
  issuer                    = "https://token.actions.githubusercontent.com"
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = "repo:ecillie/hockey-analytics:environment:nonprod"
}

resource "azurerm_federated_identity_credential" "github_prod" {
  name                      = "github-prod"
  user_assigned_identity_id = azurerm_user_assigned_identity.github_prod.id
  issuer                    = "https://token.actions.githubusercontent.com"
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = "repo:ecillie/hockey-analytics:environment:prod"
}

resource "azurerm_role_assignment" "github_nonprod_contributor" {
  scope                = azurerm_resource_group.nonprod.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.github_nonprod.principal_id
}

resource "azurerm_role_assignment" "github_prod_contributor" {
  scope                = azurerm_resource_group.prod.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.github_prod.principal_id
}

resource "azurerm_role_assignment" "github_nonprod_state" {
  scope                = azurerm_storage_container.nonprod_state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.github_nonprod.principal_id
}

resource "azurerm_role_assignment" "github_prod_state" {
  scope                = azurerm_storage_container.prod_state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.github_prod.principal_id
}

# Allow each deployment identity to manage role assignments
# within its own environment's resource group.

resource "azurerm_role_assignment" "github_nonprod_rbac" {
  scope                = azurerm_resource_group.nonprod.id
  role_definition_name = "Role Based Access Control Administrator"
  principal_id         = azurerm_user_assigned_identity.github_nonprod.principal_id
}

resource "azurerm_role_assignment" "github_prod_rbac" {
  scope                = azurerm_resource_group.prod.id
  role_definition_name = "Role Based Access Control Administrator"
  principal_id         = azurerm_user_assigned_identity.github_prod.principal_id
}

# Read information about the Azure identity running bootstrap.

data "azurerm_client_config" "current" {}

# Allow that identity to manage the bootstrap state file.

resource "azurerm_role_assignment" "bootstrap_state" {
  scope                = azurerm_storage_container.terraform_state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

# Let that identity read and write the nonprod and prod env state,
# so local plans of the env roots do not return 403.

resource "azurerm_role_assignment" "operator_nonprod_state" {
  scope                = azurerm_storage_container.nonprod_state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "operator_prod_state" {
  scope                = azurerm_storage_container.prod_state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}
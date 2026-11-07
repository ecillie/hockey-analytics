data "azurerm_client_config" "current" {}

resource "azurerm_log_analytics_workspace" "this" {
  name                = "${var.name_prefix}-${var.environment}-logs"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = 31
  daily_quota_gb      = var.log_daily_quota_gb
  tags                = var.tags
}

resource "azurerm_application_insights" "this" {
  name                = "${var.name_prefix}-${var.environment}-appi"
  resource_group_name = var.resource_group_name
  location            = var.location
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.this.id
  tags                = var.tags
}

resource "azurerm_key_vault" "this" {
  name                       = var.key_vault_name
  resource_group_name        = var.resource_group_name
  location                   = var.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = var.environment == "prod"
  tags                       = var.tags
}

resource "azurerm_role_assignment" "operator_secrets_officer" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = var.operator_principal_id
}

resource "azurerm_role_assignment" "deployer_secrets_officer" {
  count = data.azurerm_client_config.current.object_id == var.operator_principal_id ? 0 : 1

  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_key_vault_secret" "appinsights_connection_string" {
  name         = "applicationinsights-connection-string"
  key_vault_id = azurerm_key_vault.this.id
  value        = azurerm_application_insights.this.connection_string

  depends_on = [azurerm_role_assignment.deployer_secrets_officer]
}

output "key_vault_id" {
  description = "Key Vault resource ID."
  value       = azurerm_key_vault.this.id
}

output "key_vault_uri" {
  description = "Key Vault URI."
  value       = azurerm_key_vault.this.vault_uri
}

output "log_analytics_workspace_id" {
  description = "Log Analytics workspace resource ID."
  value       = azurerm_log_analytics_workspace.this.id
}

output "application_insights_id" {
  description = "Application Insights resource ID."
  value       = azurerm_application_insights.this.id
}

output "appinsights_connection_string_secret_id" {
  description = "Versionless Key Vault secret ID holding the Application Insights connection string."
  value       = azurerm_key_vault_secret.appinsights_connection_string.versionless_id
}

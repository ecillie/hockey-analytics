terraform {
  required_version = "~> 1.17.1"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.0"
    }
  }

  backend "azurerm" {
    resource_group_name  = "hockey-analytics-shared"
    storage_account_name = "hockeyanalyticstfstate"
    container_name       = "tfstate-nonprod"
    key                  = "environment.tfstate"
    use_azuread_auth     = true
  }
}

provider "azurerm" {
  features {}

  subscription_id     = var.subscription_id
  storage_use_azuread = true
}

variable "subscription_id" {
  type        = string
  description = "Azure subscription ID. Null falls back to ARM_SUBSCRIPTION_ID."
  default     = null
}

variable "operator_principal_id" {
  type        = string
  description = "Object ID of the operator granted Key Vault Secrets Officer."
}

variable "alert_email_addresses" {
  type        = list(string)
  description = "Email addresses notified by the alerting action group."
  default     = []
}

variable "database_secret_ready" {
  type        = bool
  description = "Set true once Key Vault secret database-url exists."
  default     = false
}

module "environment" {
  source = "../../modules/environment"

  environment                  = "nonprod"
  resource_group_name          = "hockey-analytics-nonprod"
  key_vault_name               = "hockey-analytics-np-kv"
  storage_account_name         = "hockeyanalyticsnpst"
  log_daily_quota_gb           = 0.05
  preview_environments_enabled = true
  operator_principal_id        = var.operator_principal_id
  alert_email_addresses        = var.alert_email_addresses
  database_secret_ready        = var.database_secret_ready
}

output "key_vault_name" {
  description = "Key Vault name."
  value       = module.environment.key_vault_name
}

output "api_url" {
  description = "HTTPS URL of the API Container App."
  value       = module.environment.api_url
}

output "static_web_app_default_host_name" {
  description = "Default host name of the Static Web App."
  value       = module.environment.static_web_app_default_host_name
}

output "managed_identity_client_id" {
  description = "User-assigned managed identity client ID."
  value       = module.environment.managed_identity_client_id
}

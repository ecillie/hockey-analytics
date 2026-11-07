variable "environment" {
  type        = string
  description = "Environment tier, nonprod or prod."

  validation {
    condition     = contains(["nonprod", "prod"], var.environment)
    error_message = "environment must be nonprod or prod."
  }
}

variable "resource_group_name" {
  type        = string
  description = "Name of the existing resource group the module deploys into."
}

variable "location" {
  type        = string
  description = "Azure region."
  default     = "eastus"
}

variable "name_prefix" {
  type        = string
  description = "Prefix for resource names."
  default     = "hockey-analytics"
}

variable "key_vault_name" {
  type        = string
  description = "Globally unique Key Vault name."
}

variable "log_daily_quota_gb" {
  type        = number
  description = "Daily ingestion cap of the Log Analytics workspace in GB."
}

variable "operator_principal_id" {
  type        = string
  description = "Object ID of the operator granted Key Vault Secrets Officer."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to all resources."
  default     = {}
}

variable "storage_account_name" {
  type        = string
  description = "Globally unique storage account name, 3-24 lowercase letters and digits."

  validation {
    condition     = can(regex("^[a-z0-9]{3,24}$", var.storage_account_name))
    error_message = "storage_account_name must be 3-24 lowercase letters and digits."
  }
}

variable "container_image" {
  type        = string
  description = "Initial container image for the API app and ingestion job. Later image changes are ignored by Terraform."
  default     = "mcr.microsoft.com/k8se/quickstart:latest"
}

variable "database_secret_ready" {
  type        = bool
  description = "Set true once Key Vault secret database-url exists, to wire DATABASE_URL into the API app and job."
  default     = false
}

variable "static_web_app_location" {
  type        = string
  description = "Azure region for the Static Web App, which is available in a limited set of regions."
  default     = "eastus2"
}

variable "preview_environments_enabled" {
  type        = bool
  description = "Whether the Static Web App allows preview environments."
  default     = false
}

variable "ingestion_timeout_seconds" {
  type        = number
  description = "Replica timeout of the manual ingestion job in seconds."
  default     = 1800
}

variable "alert_email_addresses" {
  type        = list(string)
  description = "Email addresses notified by the alerting action group."
  default     = []

  validation {
    condition     = alltrue([for address in var.alert_email_addresses : can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", address))])
    error_message = "Each alert_email_addresses entry must look like an email address."
  }
}

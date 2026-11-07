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

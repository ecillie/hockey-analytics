variable "resource_group_name" {
  description = "Resource group that holds the shared Postgres server."
  type        = string
  default     = "hockey-analytics-shared"
}

variable "location" {
  description = "Azure region for the server."
  type        = string
  default     = "eastus"
}

variable "server_name" {
  description = "Globally unique name of the Postgres Flexible Server."
  type        = string
}

variable "operator_ip" {
  description = "IPv4 address of the operator, the only address the firewall admits."
  type        = string

  validation {
    condition     = can(regex("^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])$", var.operator_ip))
    error_message = "operator_ip must be a single IPv4 address such as 203.0.113.7."
  }
}

variable "key_vault_names" {
  description = "Key Vault name per environment, keyed nonprod and prod."
  type        = map(string)

  validation {
    condition     = length(setsubtract(["nonprod", "prod"], keys(var.key_vault_names))) == 0 && length(setsubtract(keys(var.key_vault_names), ["nonprod", "prod"])) == 0
    error_message = "key_vault_names must have exactly the keys nonprod and prod."
  }
}

variable "postgres_version" {
  description = "Postgres major version."
  type        = string
  default     = "16"
}

variable "tags" {
  description = "Tags applied to every taggable resource."
  type        = map(string)
  default     = {}
}

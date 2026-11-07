terraform {
  required_version = "~> 1.17.1"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    postgresql = {
      source  = "cyrilgdn/postgresql"
      version = "~> 1.0"
    }
  }

  backend "azurerm" {
    resource_group_name  = "hockey-analytics-shared"
    storage_account_name = "hockeyanalyticstfstate"
    container_name       = "tfstate"
    key                  = "shared.tfstate"
    use_azuread_auth     = true
  }
}

provider "azurerm" {
  features {}

  subscription_id = var.subscription_id
}

provider "postgresql" {
  host      = module.shared.server_fqdn
  port      = 5432
  username  = module.shared.administrator_login
  password  = module.shared.administrator_password
  sslmode   = "require"
  superuser = false
}

variable "subscription_id" {
  type        = string
  description = "Azure subscription ID. Null falls back to ARM_SUBSCRIPTION_ID."
  default     = null
}

variable "operator_ip" {
  type        = string
  description = "IPv4 address of the operator, the only address the Postgres firewall admits."
}

module "shared" {
  source = "../../modules/shared"

  server_name = "hockey-analytics-pg"
  operator_ip = var.operator_ip
  key_vault_names = {
    nonprod = "hockey-analytics-np-kv"
    prod    = "hockey-analytics-prd-kv"
  }
}

output "server_fqdn" {
  description = "Fully qualified domain name of the Postgres server."
  value       = module.shared.server_fqdn
}

resource "azurerm_resource_group" "shared" {
  name     = "hockey-analytics-shared"
  location = "eastus"
}

resource "azurerm_resource_group" "nonprod" {
  name     = "hockey-analytics-nonprod"
  location = "eastus"
}

resource "azurerm_resource_group" "prod" {
  name     = "hockey-analytics-prod"
  location = "eastus"
}

resource "azurerm_storage_account" "terraform_state" {
  name                     = var.state_storage_account_name
  resource_group_name      = azurerm_resource_group.shared.name
  location                 = azurerm_resource_group.shared.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false

  blob_properties {
    versioning_enabled = true

    delete_retention_policy {
      days = 30
    }

    container_delete_retention_policy {
      days = 30
    }
  }

  # Losing this account loses every environment's state.
  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_storage_container" "terraform_state" {
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.terraform_state.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "nonprod_state" {
  name                  = "tfstate-nonprod"
  storage_account_id    = azurerm_storage_account.terraform_state.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "prod_state" {
  name                  = "tfstate-prod"
  storage_account_id    = azurerm_storage_account.terraform_state.id
  container_access_type = "private"
}
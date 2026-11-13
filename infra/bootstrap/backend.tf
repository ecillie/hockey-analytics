terraform {
  backend "azurerm" {
    resource_group_name  = "hockey-analytics-shared"
    storage_account_name = "hockeyanalyticstfstate"
    container_name       = "tfstate"
    key                  = "bootstrap.tfstate"
    use_azuread_auth     = true
  }
}

provider "azurerm" {
  features {}

  subscription_id = var.subscription_id

  # The GitHub deploy identities are scoped to their resource groups and
  # cannot register providers, so register everything 1.0.2 uses here.
  resource_providers_to_register = [
    "Microsoft.AlertsManagement",
    "Microsoft.App",
    "Microsoft.Consumption",
    "Microsoft.DBforPostgreSQL",
    "Microsoft.Insights",
    "Microsoft.KeyVault",
    "Microsoft.ManagedIdentity",
    "Microsoft.OperationalInsights",
    "Microsoft.Storage",
    "Microsoft.Web",
  ]
}

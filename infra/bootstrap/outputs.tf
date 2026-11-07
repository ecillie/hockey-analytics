output "resource_group_name" {
  description = "Resource group containing the Terraform state storage."
  value       = azurerm_resource_group.shared.name
}

output "state_storage_account_name" {
  description = "Storage account containing Terraform state."
  value       = azurerm_storage_account.terraform_state.name
}

output "state_container_name" {
  description = "Blob container containing Terraform state."
  value       = azurerm_storage_container.terraform_state.name
}

output "nonprod_state_container_name" {
  description = "Blob container for nonprod environment state."
  value       = azurerm_storage_container.nonprod_state.name
}

output "prod_state_container_name" {
  description = "Blob container for prod environment state."
  value       = azurerm_storage_container.prod_state.name
}

output "azure_tenant_id" {
  description = "AZURE_TENANT_ID for both GitHub Environments."
  value       = data.azurerm_client_config.current.tenant_id
}

output "azure_subscription_id" {
  description = "AZURE_SUBSCRIPTION_ID for both GitHub Environments."
  value       = var.subscription_id
}

output "github_nonprod_client_id" {
  description = "AZURE_CLIENT_ID for the nonprod GitHub Environment."
  value       = azurerm_user_assigned_identity.github_nonprod.client_id
}

output "github_prod_client_id" {
  description = "AZURE_CLIENT_ID for the prod GitHub Environment."
  value       = azurerm_user_assigned_identity.github_prod.client_id
}

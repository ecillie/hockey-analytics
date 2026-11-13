resource "azurerm_storage_account" "this" {
  name                            = var.storage_account_name
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false
  tags                            = var.tags
}

resource "azurerm_storage_container" "ingestion_data" {
  name                  = "ingestion-data"
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "ml_artifacts" {
  name                  = "ml-artifacts"
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}

# The operator uploads season CSVs and ML artifacts with scripts/upload-blob-data.sh.
resource "azurerm_role_assignment" "operator_blob_contributor" {
  scope                = azurerm_storage_account.this.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.operator_principal_id
}

output "storage_account_id" {
  description = "Storage account resource ID."
  value       = azurerm_storage_account.this.id
}

output "storage_account_name" {
  description = "Storage account name."
  value       = azurerm_storage_account.this.name
}

output "ingestion_data_container_url" {
  description = "Blob container URL the ingestion job downloads its season CSVs from."
  value       = local.ingestion_data_url
}

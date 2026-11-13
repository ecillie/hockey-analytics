mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id = "00000000-0000-0000-0000-000000000001"
      object_id = "00000000-0000-0000-0000-000000000002"
    }
  }

  override_resource {
    target          = azurerm_key_vault.this
    override_during = plan
    values = {
      id = "/subscriptions/s/resourceGroups/rg-test/providers/Microsoft.KeyVault/vaults/kv-test-nonprod"
    }
  }

  override_resource {
    target          = azurerm_storage_account.this
    override_during = plan
    values = {
      id = "/subscriptions/s/resourceGroups/rg-test/providers/Microsoft.Storage/storageAccounts/sttestnonprod"
    }
  }
}

variables {
  environment           = "nonprod"
  resource_group_name   = "rg-test"
  key_vault_name        = "kv-test-nonprod"
  log_daily_quota_gb    = 2
  operator_principal_id = "00000000-0000-0000-0000-000000000003"
  storage_account_name  = "sttestnonprod"
}

run "identity" {
  command = plan

  assert {
    condition     = azurerm_user_assigned_identity.app.name == "hockey-analytics-nonprod-id"
    error_message = "Managed identity must use the name_prefix-environment- prefix."
  }
}

run "storage" {
  command = plan

  assert {
    condition     = azurerm_storage_account.this.name == var.storage_account_name
    error_message = "Storage account name must equal storage_account_name."
  }

  assert {
    condition     = azurerm_storage_account.this.allow_nested_items_to_be_public == false
    error_message = "Public blob access must be off."
  }

  assert {
    condition     = azurerm_storage_account.this.min_tls_version == "TLS1_2"
    error_message = "Minimum TLS version must be TLS1_2."
  }

  assert {
    condition     = azurerm_storage_container.ingestion_data.name == "ingestion-data" && azurerm_storage_container.ingestion_data.container_access_type == "private"
    error_message = "Season CSVs must live in the private ingestion-data container."
  }

  assert {
    condition     = azurerm_storage_container.ml_artifacts.name == "ml-artifacts" && azurerm_storage_container.ml_artifacts.container_access_type == "private"
    error_message = "ML artifacts must live in the private ml-artifacts container."
  }

  assert {
    condition     = azurerm_role_assignment.operator_blob_contributor.role_definition_name == "Storage Blob Data Contributor" && azurerm_role_assignment.operator_blob_contributor.principal_id == var.operator_principal_id && azurerm_role_assignment.operator_blob_contributor.scope == azurerm_storage_account.this.id
    error_message = "The operator must be able to upload blobs to this storage account only."
  }
}

run "role_scopes" {
  command = plan

  assert {
    condition     = azurerm_role_assignment.app_secrets_user.role_definition_name == "Key Vault Secrets User" && azurerm_role_assignment.app_secrets_user.scope == azurerm_key_vault.this.id
    error_message = "Identity must hold Key Vault Secrets User scoped to the Key Vault."
  }

  assert {
    condition     = azurerm_role_assignment.app_blob_reader.role_definition_name == "Storage Blob Data Reader" && azurerm_role_assignment.app_blob_reader.scope == azurerm_storage_account.this.id
    error_message = "Identity must hold Storage Blob Data Reader scoped to the storage account."
  }

  assert {
    condition     = strcontains(azurerm_role_assignment.app_secrets_user.scope, "/providers/Microsoft.KeyVault/vaults/")
    error_message = "Key Vault role must not be at resource-group scope."
  }

  assert {
    condition     = strcontains(azurerm_role_assignment.app_blob_reader.scope, "/providers/Microsoft.Storage/storageAccounts/")
    error_message = "Storage role must not be at resource-group scope."
  }
}

run "invalid_storage_account_name" {
  command = plan

  variables {
    storage_account_name = "Bad-Name"
  }

  expect_failures = [var.storage_account_name]
}

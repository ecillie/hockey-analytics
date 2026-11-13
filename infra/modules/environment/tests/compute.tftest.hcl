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
      id        = "/subscriptions/s/resourceGroups/rg-test/providers/Microsoft.KeyVault/vaults/kv-test-nonprod"
      vault_uri = "https://kv-test-nonprod.vault.azure.net/"
    }
  }

  override_resource {
    target          = azurerm_user_assigned_identity.app
    override_during = plan
    values = {
      id = "/subscriptions/s/resourceGroups/rg-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-test"
    }
  }

  override_resource {
    target          = azurerm_log_analytics_workspace.this
    override_during = plan
    values = {
      id = "/subscriptions/s/resourceGroups/rg-test/providers/Microsoft.OperationalInsights/workspaces/logs-test"
    }
  }

  override_resource {
    target          = azurerm_static_web_app.this
    override_during = plan
    values = {
      default_host_name = "gentle-sky-0a1b2c3d4.4.azurestaticapps.net"
    }
  }

  override_resource {
    target          = azurerm_storage_account.this
    override_during = plan
    values = {
      id                    = "/subscriptions/s/resourceGroups/rg-test/providers/Microsoft.Storage/storageAccounts/sttestnonprod"
      primary_blob_endpoint = "https://sttestnonprod.blob.core.windows.net/"
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

run "compute_without_database_secret" {
  command = plan

  assert {
    condition     = azurerm_container_app.api.template[0].min_replicas == 0
    error_message = "API app must scale to zero."
  }

  assert {
    condition     = azurerm_container_app.api.ingress[0].external_enabled && azurerm_container_app.api.ingress[0].target_port == 8000
    error_message = "API ingress must be external on port 8000."
  }

  assert {
    condition     = azurerm_container_app.api.template[0].container[0].liveness_probe[0].path == "/api/health" && azurerm_container_app.api.template[0].container[0].readiness_probe[0].path == "/api/health"
    error_message = "Probes must hit /api/health."
  }

  assert {
    condition     = azurerm_container_app.api.template[0].container[0].image == "mcr.microsoft.com/k8se/quickstart:latest"
    error_message = "API app must start from the placeholder image."
  }

  assert {
    condition     = length(azurerm_container_app.api.secret) == 1 && length(azurerm_container_app.api.template[0].container[0].env) == 3
    error_message = "Without database_secret_ready only the App Insights secret and ENV/connection/CORS env vars are set."
  }

  assert {
    condition     = length(azurerm_container_app_job.ingestion.secret) == 1 && length(azurerm_container_app_job.ingestion.template[0].container[0].env) == 4
    error_message = "Job must omit DATABASE_URL when database_secret_ready is false."
  }

  assert {
    condition = anytrue([
      for env in azurerm_container_app_job.ingestion.template[0].container[0].env :
      env.name == "TRADEVALUE_DATA_BLOB_URL" && env.value == "https://sttestnonprod.blob.core.windows.net/ingestion-data"
    ])
    error_message = "Job must download season CSVs from the ingestion-data container."
  }

  assert {
    condition = anytrue([
      for env in azurerm_container_app_job.ingestion.template[0].container[0].env :
      env.name == "AZURE_CLIENT_ID" && env.value == azurerm_user_assigned_identity.app.client_id
    ])
    error_message = "Job must authenticate to storage as the managed identity."
  }

  assert {
    condition     = azurerm_container_app_job.ingestion.replica_timeout_in_seconds == 1800 && length(azurerm_container_app_job.ingestion.manual_trigger_config) == 1
    error_message = "Job must be manual with an 1800-second timeout."
  }

  assert {
    condition     = azurerm_container_app_environment.this.log_analytics_workspace_id == azurerm_log_analytics_workspace.this.id
    error_message = "Environment must log to the module workspace."
  }

  assert {
    condition     = tolist(azurerm_container_app.api.identity[0].identity_ids)[0] == azurerm_user_assigned_identity.app.id
    error_message = "API app must run as the managed identity."
  }

  assert {
    condition     = azurerm_static_web_app.this.location == "eastus2" && azurerm_static_web_app.this.sku_tier == "Free" && azurerm_static_web_app.this.preview_environments_enabled == false
    error_message = "Static Web App must be Free in eastus2 with previews off by default."
  }
}

run "compute_with_database_secret" {
  command = plan

  variables {
    database_secret_ready        = true
    preview_environments_enabled = true
  }

  assert {
    condition = (
      length(azurerm_container_app.api.secret) == 2 &&
      length(azurerm_container_app.api.template[0].container[0].env) == 5 &&
      length(azurerm_container_app_job.ingestion.secret) == 2 &&
      length(azurerm_container_app_job.ingestion.template[0].container[0].env) == 5
    )
    error_message = "DATABASE_URL secret and env must be added when database_secret_ready is true."
  }

  assert {
    condition     = azurerm_static_web_app.this.preview_environments_enabled == true
    error_message = "preview_environments_enabled must reach the Static Web App."
  }

  assert {
    condition = anytrue([
      for env in azurerm_container_app.api.template[0].container[0].env :
      env.name == "CORS_ORIGIN_REGEX" && env.value == "^https://gentle-sky-0a1b2c3d4-[0-9]+\\.[a-z0-9]+(\\.[0-9]+)?\\.azurestaticapps\\.net$"
    ])
    error_message = "With previews on, the API must allow only this Static Web App's preview origins."
  }
}

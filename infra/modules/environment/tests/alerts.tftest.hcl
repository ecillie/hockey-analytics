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

run "alerts" {
  command = plan

  variables {
    alert_email_addresses = ["a@example.com", "b@example.com"]
  }

  assert {
    condition     = length(azurerm_monitor_action_group.alerts.email_receiver) == 2
    error_message = "Each alert email address must become a receiver."
  }

  assert {
    condition     = azurerm_monitor_metric_alert.api_5xx.criteria[0].metric_name == "Requests" && one(azurerm_monitor_metric_alert.api_5xx.criteria[0].dimension).name == "statusCodeCategory" && contains(one(azurerm_monitor_metric_alert.api_5xx.criteria[0].dimension).values, "5xx")
    error_message = "API alert must fire on Requests with statusCodeCategory 5xx."
  }

  assert {
    condition     = azurerm_monitor_metric_alert.ingestion_failed.criteria[0].metric_name == "Executions" && one(azurerm_monitor_metric_alert.ingestion_failed.criteria[0].dimension).name == "state" && contains(one(azurerm_monitor_metric_alert.ingestion_failed.criteria[0].dimension).values, "Failed")
    error_message = "Ingestion alert must fire on Executions with state Failed."
  }

  assert {
    condition     = output.key_vault_name == "kv-test-nonprod"
    error_message = "key_vault_name output must be the vault name."
  }
}

run "alerts_invalid_email" {
  command = plan

  variables {
    alert_email_addresses = ["not-an-email"]
  }

  expect_failures = [var.alert_email_addresses]
}

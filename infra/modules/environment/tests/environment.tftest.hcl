mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id = "00000000-0000-0000-0000-000000000001"
      object_id = "00000000-0000-0000-0000-000000000002"
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

run "observability" {
  command = plan

  assert {
    condition     = azurerm_log_analytics_workspace.this.retention_in_days == 31
    error_message = "Retention must be 31 days."
  }

  assert {
    condition     = azurerm_log_analytics_workspace.this.daily_quota_gb == var.log_daily_quota_gb
    error_message = "Daily cap must equal log_daily_quota_gb."
  }

  assert {
    condition     = azurerm_application_insights.this.application_type == "web"
    error_message = "Application Insights must be type web."
  }

  assert {
    condition     = azurerm_application_insights.this.name == "hockey-analytics-nonprod-appi"
    error_message = "Unexpected Application Insights name."
  }
}

run "key_vault" {
  command = plan

  assert {
    condition     = azurerm_key_vault.this.sku_name == "standard" && azurerm_key_vault.this.rbac_authorization_enabled
    error_message = "Key Vault must be Standard with RBAC authorization."
  }

  assert {
    condition     = azurerm_role_assignment.operator_secrets_officer.role_definition_name == "Key Vault Secrets Officer" && azurerm_role_assignment.operator_secrets_officer.principal_id == var.operator_principal_id
    error_message = "Operator must hold Key Vault Secrets Officer."
  }

  assert {
    condition     = length(azurerm_role_assignment.deployer_secrets_officer) == 1 && azurerm_role_assignment.deployer_secrets_officer[0].role_definition_name == "Key Vault Secrets Officer" && azurerm_role_assignment.deployer_secrets_officer[0].principal_id == "00000000-0000-0000-0000-000000000002"
    error_message = "Deploying identity must hold Key Vault Secrets Officer."
  }

  assert {
    condition     = azurerm_key_vault_secret.appinsights_connection_string.name == "applicationinsights-connection-string"
    error_message = "Connection string secret name is wrong."
  }
}

run "key_vault_deployer_is_operator" {
  command = plan

  override_data {
    target = data.azurerm_client_config.current
    values = {
      tenant_id = "00000000-0000-0000-0000-000000000001"
      object_id = "00000000-0000-0000-0000-000000000003"
    }
  }

  assert {
    condition     = length(azurerm_role_assignment.deployer_secrets_officer) == 0 && azurerm_role_assignment.operator_secrets_officer.role_definition_name == "Key Vault Secrets Officer"
    error_message = "When the deployer is the operator, exactly one Secrets Officer assignment must be planned."
  }
}

run "purge_protection_prod" {
  command = plan

  variables {
    environment = "prod"
  }

  assert {
    condition     = azurerm_key_vault.this.purge_protection_enabled
    error_message = "Prod Key Vault must have purge protection enabled."
  }
}

run "purge_protection_nonprod" {
  command = plan

  assert {
    condition     = !azurerm_key_vault.this.purge_protection_enabled
    error_message = "Nonprod Key Vault must not have purge protection enabled."
  }
}

run "invalid_environment" {
  command = plan

  variables {
    environment = "staging"
  }

  expect_failures = [var.environment]
}

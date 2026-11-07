mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      subscription_id = "00000000-0000-0000-0000-000000000001"
      tenant_id       = "00000000-0000-0000-0000-000000000002"
    }
  }
}
mock_provider "random" {}
mock_provider "postgresql" {}

variables {
  server_name = "hockey-analytics-pg"
  operator_ip = "203.0.113.7"
  key_vault_names = {
    nonprod = "kv-nonprod"
    prod    = "kv-prod"
  }
}

run "server_and_databases" {
  command = plan

  assert {
    condition     = azurerm_postgresql_flexible_server.this.sku_name == "B_Standard_B1ms" && azurerm_postgresql_flexible_server.this.location == "eastus" && azurerm_postgresql_flexible_server.this.resource_group_name == "hockey-analytics-shared"
    error_message = "Server must be B1ms in eastus in the shared resource group."
  }

  assert {
    condition     = azurerm_postgresql_flexible_server_database.this["nonprod"].name == "nonprod" && azurerm_postgresql_flexible_server_database.this["prod"].name == "prod"
    error_message = "Databases nonprod and prod are required."
  }
}

run "grants_isolate_databases" {
  command = plan

  assert {
    condition     = postgresql_grant.connect["nonprod"].database == "nonprod" && postgresql_grant.connect["prod"].database == "prod" && postgresql_grant.connect["prod"].role == "prod_app"
    error_message = "Each login gets CONNECT on its own database only."
  }

  assert {
    condition     = toset(postgresql_grant.schema["nonprod"].privileges) == toset(["USAGE", "CREATE"]) && postgresql_grant.schema["prod"].schema == "public"
    error_message = "Each login gets USAGE and CREATE on its public schema."
  }

  assert {
    condition     = alltrue([for g in postgresql_grant.public_connect_revoke : g.role == "public" && length(g.privileges) == 0 && g.object_type == "database"]) && length(postgresql_grant.public_connect_revoke) == 2
    error_message = "PUBLIC must be revoked on both databases."
  }
}

run "single_operator_firewall_rule" {
  command = plan

  assert {
    condition     = azurerm_postgresql_flexible_server_firewall_rule.operator.start_ip_address == "203.0.113.7" && azurerm_postgresql_flexible_server_firewall_rule.operator.end_ip_address == "203.0.113.7"
    error_message = "Firewall must admit only operator_ip."
  }
}

run "database_url_secrets" {
  command = plan

  assert {
    condition     = azurerm_key_vault_secret.database_url["prod"].name == "database-url" && azurerm_key_vault_secret.database_url["prod"].key_vault_id == "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/hockey-analytics-prod/providers/Microsoft.KeyVault/vaults/kv-prod"
    error_message = "Prod secret must target the prod vault ID."
  }

  assert {
    condition     = azurerm_key_vault_secret.database_url["nonprod"].key_vault_id == "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/hockey-analytics-nonprod/providers/Microsoft.KeyVault/vaults/kv-nonprod"
    error_message = "Nonprod secret must target the nonprod vault ID."
  }
}

run "rejects_bad_operator_ip" {
  command = plan

  variables {
    operator_ip = "0.0.0.0/0"
  }

  expect_failures = [var.operator_ip]
}

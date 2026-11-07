data "azurerm_client_config" "current" {}

locals {
  environments   = toset(["nonprod", "prod"])
  administrator  = "pgadmin"
  subscription   = data.azurerm_client_config.current.subscription_id
  vault_ids      = { for env in local.environments : env => "/subscriptions/${local.subscription}/resourceGroups/${var.key_vaults[env].resource_group_name}/providers/Microsoft.KeyVault/vaults/${var.key_vaults[env].name}" }
  database_names = { for env in local.environments : env => env }
}

resource "random_password" "administrator" {
  length  = 32
  special = false
}

resource "random_password" "login" {
  for_each = local.environments

  length  = 32
  special = false
}

resource "azurerm_postgresql_flexible_server" "this" {
  name                          = var.server_name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  version                       = var.postgres_version
  sku_name                      = "B_Standard_B1ms"
  storage_mb                    = 32768
  administrator_login           = local.administrator
  administrator_password        = random_password.administrator.result
  public_network_access_enabled = true
  zone                          = "1"
  tags                          = var.tags
}

resource "azurerm_postgresql_flexible_server_database" "this" {
  for_each = local.environments

  name      = local.database_names[each.key]
  server_id = azurerm_postgresql_flexible_server.this.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "operator" {
  name             = "operator"
  server_id        = azurerm_postgresql_flexible_server.this.id
  start_ip_address = var.operator_ip
  end_ip_address   = var.operator_ip
}

resource "postgresql_role" "login" {
  for_each = local.environments

  name     = "${each.key}_app"
  login    = true
  password = random_password.login[each.key].result

  depends_on = [azurerm_postgresql_flexible_server_database.this, azurerm_postgresql_flexible_server_firewall_rule.operator]
}

resource "postgresql_grant" "public_connect_revoke" {
  for_each = local.environments

  database    = azurerm_postgresql_flexible_server_database.this[each.key].name
  role        = "public"
  object_type = "database"
  privileges  = []

  depends_on = [azurerm_postgresql_flexible_server_firewall_rule.operator]
}

resource "postgresql_grant" "connect" {
  for_each = local.environments

  database    = azurerm_postgresql_flexible_server_database.this[each.key].name
  role        = postgresql_role.login[each.key].name
  object_type = "database"
  privileges  = ["CONNECT"]

  depends_on = [azurerm_postgresql_flexible_server_firewall_rule.operator]
}

resource "postgresql_grant" "schema" {
  for_each = local.environments

  database    = azurerm_postgresql_flexible_server_database.this[each.key].name
  role        = postgresql_role.login[each.key].name
  schema      = "public"
  object_type = "schema"
  privileges  = ["USAGE", "CREATE"]

  depends_on = [azurerm_postgresql_flexible_server_firewall_rule.operator]
}

resource "azurerm_key_vault_secret" "database_url" {
  for_each = local.environments

  name         = "database-url"
  key_vault_id = local.vault_ids[each.key]
  value        = "postgresql://${postgresql_role.login[each.key].name}:${random_password.login[each.key].result}@${azurerm_postgresql_flexible_server.this.fqdn}:5432/${azurerm_postgresql_flexible_server_database.this[each.key].name}?sslmode=require"
}

output "server_fqdn" {
  description = "Fully qualified domain name of the Postgres server."
  value       = azurerm_postgresql_flexible_server.this.fqdn
}

output "server_id" {
  description = "Resource ID of the Postgres server."
  value       = azurerm_postgresql_flexible_server.this.id
}

output "administrator_login" {
  description = "Server administrator login."
  value       = azurerm_postgresql_flexible_server.this.administrator_login
}

output "administrator_password" {
  description = "Server administrator password."
  value       = random_password.administrator.result
  sensitive   = true
}

output "database_names" {
  description = "Database name per environment."
  value       = { for env, db in azurerm_postgresql_flexible_server_database.this : env => db.name }
}

locals {
  appinsights_secret_ref = "${azurerm_key_vault.this.vault_uri}secrets/${azurerm_key_vault_secret.appinsights_connection_string.name}"
  database_secret_ref    = "${azurerm_key_vault.this.vault_uri}secrets/database-url"
}

resource "azurerm_container_app_environment" "this" {
  name                       = "${var.name_prefix}-${var.environment}-cae"
  resource_group_name        = var.resource_group_name
  location                   = var.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
  tags                       = var.tags
}

resource "azurerm_container_app" "api" {
  depends_on = [azurerm_role_assignment.app_secrets_user]

  name                         = "${var.name_prefix}-${var.environment}-api"
  resource_group_name          = var.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.this.id
  revision_mode                = "Single"
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  secret {
    name                = "appinsights-connection-string"
    key_vault_secret_id = local.appinsights_secret_ref
    identity            = azurerm_user_assigned_identity.app.id
  }

  dynamic "secret" {
    for_each = var.database_secret_ready ? [1] : []

    content {
      name                = "database-url"
      key_vault_secret_id = local.database_secret_ref
      identity            = azurerm_user_assigned_identity.app.id
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 0
    max_replicas = 2

    container {
      name   = "api"
      image  = var.container_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "ENV"
        value = var.environment
      }

      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "appinsights-connection-string"
      }

      dynamic "env" {
        for_each = var.database_secret_ready ? [1] : []

        content {
          name        = "DATABASE_URL"
          secret_name = "database-url"
        }
      }

      liveness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/api/health"
      }

      readiness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/api/health"
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}

resource "azurerm_container_app_job" "ingestion" {
  depends_on = [azurerm_role_assignment.app_secrets_user]

  name                         = "${var.name_prefix}-${var.environment}-ingest"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  container_app_environment_id = azurerm_container_app_environment.this.id
  replica_timeout_in_seconds   = var.ingestion_timeout_seconds
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  secret {
    name                = "appinsights-connection-string"
    key_vault_secret_id = local.appinsights_secret_ref
    identity            = azurerm_user_assigned_identity.app.id
  }

  dynamic "secret" {
    for_each = var.database_secret_ready ? [1] : []

    content {
      name                = "database-url"
      key_vault_secret_id = local.database_secret_ref
      identity            = azurerm_user_assigned_identity.app.id
    }
  }

  template {
    container {
      name   = "ingestion"
      image  = var.container_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "ENV"
        value = var.environment
      }

      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "appinsights-connection-string"
      }

      dynamic "env" {
        for_each = var.database_secret_ready ? [1] : []

        content {
          name        = "DATABASE_URL"
          secret_name = "database-url"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}

output "api_url" {
  description = "HTTPS URL of the API Container App."
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "container_app_environment_id" {
  description = "Container Apps environment resource ID."
  value       = azurerm_container_app_environment.this.id
}

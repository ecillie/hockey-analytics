resource "azurerm_monitor_action_group" "alerts" {
  name                = "${var.name_prefix}-${var.environment}-alerts"
  resource_group_name = var.resource_group_name
  short_name          = substr("tv-${var.environment}", 0, 12)
  tags                = var.tags

  dynamic "email_receiver" {
    for_each = var.alert_email_addresses

    content {
      name          = "email-${email_receiver.key}"
      email_address = email_receiver.value
    }
  }
}

resource "azurerm_monitor_metric_alert" "api_5xx" {
  name                = "${var.name_prefix}-${var.environment}-api-5xx"
  resource_group_name = var.resource_group_name
  scopes              = [azurerm_container_app.api.id]
  description         = "API Container App returned 5xx responses."
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT5M"
  tags                = var.tags

  # The "5xx" statusCodeCategory value is not enumerated in Microsoft's docs; unverified until first apply.
  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "Requests"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 0

    dimension {
      name     = "statusCodeCategory"
      operator = "Include"
      values   = ["5xx"]
    }
  }

  action {
    action_group_id = azurerm_monitor_action_group.alerts.id
  }
}

resource "azurerm_monitor_metric_alert" "ingestion_failed" {
  name                = "${var.name_prefix}-${var.environment}-ingest-failed"
  resource_group_name = var.resource_group_name
  scopes              = [azurerm_container_app_job.ingestion.id]
  description         = "Ingestion job execution failed."
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT5M"
  tags                = var.tags

  # The "Failed" state dimension value is not enumerated in Microsoft's docs; unverified until first apply.
  criteria {
    metric_namespace = "Microsoft.App/jobs"
    metric_name      = "Executions"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 0

    dimension {
      name     = "state"
      operator = "Include"
      values   = ["Failed"]
    }
  }

  action {
    action_group_id = azurerm_monitor_action_group.alerts.id
  }
}

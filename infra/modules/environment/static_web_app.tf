resource "azurerm_static_web_app" "this" {
  name                         = "${var.name_prefix}-${var.environment}-swa"
  resource_group_name          = var.resource_group_name
  location                     = var.static_web_app_location
  sku_tier                     = "Free"
  sku_size                     = "Free"
  preview_environments_enabled = var.preview_environments_enabled
  tags                         = var.tags
}

output "static_web_app_default_host_name" {
  description = "Default host name of the Static Web App."
  value       = azurerm_static_web_app.this.default_host_name
}

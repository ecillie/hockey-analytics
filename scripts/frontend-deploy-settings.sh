#!/usr/bin/env bash
# Reads one environment's frontend build and deploy settings from Azure into
# GITHUB_ENV. Requires an az login that can read the environment's resource group.
set -euo pipefail
target="${1:?usage: frontend-deploy-settings.sh nonprod|prod}"
case "$target" in nonprod | prod) ;; *) echo "Unknown environment: $target" >&2; exit 2 ;; esac
group="hockey-analytics-$target"

api_host=$(az containerapp show --name "hockey-analytics-$target-api" --resource-group "$group" \
  --query properties.configuration.ingress.fqdn --output tsv)
swa_host=$(az staticwebapp show --name "hockey-analytics-$target-swa" --resource-group "$group" \
  --query defaultHostname --output tsv)
deploy_token=$(az staticwebapp secrets list --name "hockey-analytics-$target-swa" --resource-group "$group" \
  --query properties.apiKey --output tsv)
connection_string=$(az resource show --name "hockey-analytics-$target-appi" --resource-group "$group" \
  --resource-type Microsoft.Insights/components --query properties.ConnectionString --output tsv)

for value in "$api_host" "$swa_host" "$deploy_token" "$connection_string"; do
  if [ -z "$value" ]; then echo "A $target frontend setting is empty." >&2; exit 1; fi
done
# The deploy token is a credential. The connection string ends up in the public
# bundle, but there is no reason to print it in logs.
echo "::add-mask::$deploy_token"
echo "::add-mask::$connection_string"
{
  echo "VITE_API_BASE_URL=https://$api_host"
  echo "SWA_HOST=$swa_host"
  echo "SWA_DEPLOY_TOKEN=$deploy_token"
  echo "VITE_APPINSIGHTS_CONNECTION_STRING=$connection_string"
} >> "$GITHUB_ENV"

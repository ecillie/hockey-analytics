#!/usr/bin/env bash
# Uploads the season CSVs and ML artifacts to one environment's storage account.
# Requires an az login holding Storage Blob Data Contributor on that account
# (Terraform grants it to operator_principal_id). Safe to rerun: blobs are
# overwritten in place, and blobs no longer present locally are left alone.
set -euo pipefail
cd "$(dirname "$0")/.."
target="${1:?usage: upload-blob-data.sh nonprod|prod}"
case "$target" in
  nonprod) account=hockeyanalyticsnpst ;;
  prod) account=hockeyanalyticsprdst ;;
  *) echo "Unknown environment: $target" >&2; exit 2 ;;
esac

models=(ml/models/*.joblib)
if [ ! -e "${models[0]}" ]; then
  echo "No ml/models/*.joblib found; train or restore the model first." >&2
  exit 1
fi

upload() {
  az storage blob upload-batch --auth-mode login --account-name "$account" --overwrite true \
    --only-show-errors --output none "$@"
}

# Ingestion reads this layout from TRADEVALUE_DATA_DIR, so keep backend/data's folders.
upload --destination ingestion-data --source backend/data --pattern '*.csv'
upload --destination ml-artifacts --destination-path models --source ml/models --pattern '*.joblib'
upload --destination ml-artifacts --destination-path evaluation/outputs --source ml/evaluation/outputs

for container in ingestion-data ml-artifacts; do
  echo "$container:"
  az storage blob list --auth-mode login --account-name "$account" --container-name "$container" \
    --only-show-errors --query "[].[name, properties.contentLength]" --output tsv | sed 's/^/  /'
done

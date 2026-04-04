#!/bin/bash
set -euo pipefail

NAMESPACE="n8n"
SECRET_NAME="n8n-secret"
OUTPUT_FILE="apps/n8n/sealed-secret.yaml"

if [ -z "${N8N_ENCRYPTION_KEY:-}" ]; then
  echo "N8N_ENCRYPTION_KEY environment variable is required"
  echo "Example: N8N_ENCRYPTION_KEY='your-encryption-key' $0"
  exit 1
fi

echo "Generating sealed secret for n8n..."

kubectl create secret generic "${SECRET_NAME}" \
  --namespace "${NAMESPACE}" \
  --dry-run=client \
  --from-literal=N8N_ENCRYPTION_KEY="${N8N_ENCRYPTION_KEY}" \
  -o json | kubeseal \
    --controller-name=sealed-secrets-controller \
    --controller-namespace=sealed-secrets \
    --format=yaml \
    | tee "${OUTPUT_FILE}"

echo ""
echo "SealedSecret generated: ${OUTPUT_FILE}"
echo "Namespace: ${NAMESPACE}"
echo "Secret name: ${SECRET_NAME}"

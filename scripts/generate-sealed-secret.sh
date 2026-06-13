#!/bin/bash
set -euo pipefail

NAMESPACE="kube-system"
SECRET_NAME="tunnel-credentials"

echo "🔐 Generating sealed secret for Cloudflare Tunnel..."

# Get token from Terraform
echo "📥 Fetching tunnel token from Terraform..."
TOKEN=$(cd ./terraform && terraform output -raw tunnel_token)

if [ -z "$TOKEN" ]; then
  echo "❌ Failed to get tunnel token from Terraform"
  exit 1
fi

# Generate sealed secret
echo "🔒 Creating sealed secret..."
kubectl create secret generic $SECRET_NAME \
  --namespace $NAMESPACE \
  --dry-run=client \
  --from-literal=token="$TOKEN" \
  -o json | kubeseal \
    --controller-name=sealed-secrets-controller \
    --controller-namespace=sealed-secrets \
    --format=yaml \
    | tee system/cloudflared/sealed-cloudflared-token.yaml

echo ""
echo "✅ SealedSecret generated: system/cloudflared/sealed-cloudflared-token.yaml"
echo "📝 Namespace: $NAMESPACE"
echo "📝 Secret name: $SECRET_NAME"
echo ""
echo "Next steps:"
echo "  1. Review the sealed secret"
echo "  2. Commit and push to Git"
echo "  3. ArgoCD will sync and deploy cloudflared"

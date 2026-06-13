#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_OAUTH_CLIENT_ID:?GITHUB_OAUTH_CLIENT_ID is required}"
: "${GITHUB_OAUTH_CLIENT_SECRET:?GITHUB_OAUTH_CLIENT_SECRET is required}"

output="system/argocd/argocd-sso-sealed-secret.yaml"

kubectl create secret generic argocd-secret \
  --namespace argocd \
  --dry-run=client \
  --from-literal=dex.github.clientID="${GITHUB_OAUTH_CLIENT_ID}" \
  --from-literal=dex.github.clientSecret="${GITHUB_OAUTH_CLIENT_SECRET}" \
  -o json |
  kubeseal \
    --controller-name=sealed-secrets-controller \
    --controller-namespace=sealed-secrets \
    --format=yaml |
  kubectl annotate --local -f - \
    sealedsecrets.bitnami.com/patch=true \
    -o yaml >"${output}"

printf 'Generated %s\n' "${output}"
printf 'Follow docs/security-runbook.md to enable and test SSO safely.\n'

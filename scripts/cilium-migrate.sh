#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

for tool in kubectl helm talosctl cilium jq; do
  command -v "$tool" >/dev/null || {
    echo "missing required tool: $tool" >&2
    exit 1
  }
done

helm dependency build system/cilium >/dev/null
mkdir -p .cache
helm lint system/cilium >/dev/null
helm template cilium system/cilium --namespace kube-system \
  > .cache/cilium-rendered.yaml
kubectl apply --dry-run=client -f .cache/cilium-rendered.yaml >/dev/null
if command -v kubeconform >/dev/null; then
  kubeconform -strict -summary -ignore-missing-schemas \
    .cache/cilium-rendered.yaml
fi

if [[ "${1:-}" != "--execute" ]]; then
  echo "Cilium render, schema validation, and client dry run passed."
  echo "Run with --execute and CONFIRM_CILIUM_MIGRATION=yes during the maintenance window."
  exit 0
fi

if [[ "${CONFIRM_CILIUM_MIGRATION:-}" != "yes" ]]; then
  echo "Set CONFIRM_CILIUM_MIGRATION=yes to execute the cutover." >&2
  exit 1
fi

if [[ ! -f .backups/last-successful-backup ]]; then
  echo "No successful backup marker found; run scripts/backup-pvcs.sh first." >&2
  exit 1
fi
if [[ ! -f .backups/last-successful-restore-test ]]; then
  echo "No successful restore-test marker found; rehearse scripts/restore-pvc.sh first." >&2
  exit 1
fi

backup_epoch="$(date -j -f '%Y-%m-%dT%H:%M:%SZ' "$(cat .backups/last-successful-backup)" +%s 2>/dev/null || date -d "$(cat .backups/last-successful-backup)" +%s)"
if (( $(date +%s) - backup_epoch > 86400 )); then
  echo "The latest successful backup is older than 24 hours." >&2
  exit 1
fi

nodes=()
while IFS= read -r node; do
  nodes+=("$node")
done < <(
  kubectl get nodes -o json |
    jq -r '.items[].status.addresses[] | select(.type == "InternalIP") | .address'
)
printf 'Cutting over nodes: %s\n' "${nodes[*]}"

for workload in \
  crafty-controller/crafty-controller \
  home-assistant/home-assistant \
  n8n/n8n; do
  namespace="${workload%/*}"
  deployment="${workload#*/}"
  kubectl -n "$namespace" scale deployment "$deployment" --replicas=0
done

for node in "${nodes[@]}"; do
  talosctl --nodes "$node" patch machineconfig --patch @talos/patches/cilium.yaml
done

helm upgrade --install cilium system/cilium \
  --namespace kube-system --create-namespace --wait --timeout 15m
kubectl -n kube-system delete pods -l app=flannel --ignore-not-found
kubectl get pods --all-namespaces -o json |
  jq -r '
    .items[]
    | select(.spec.hostNetwork != true)
    | select(.metadata.labels["app.kubernetes.io/part-of"] != "cilium")
    | select(.metadata.labels["k8s-app"] != "cilium")
    | "\(.metadata.namespace) \(.metadata.name)"
  ' |
  while read -r namespace pod; do
    kubectl -n "$namespace" delete pod "$pod" --wait=false
  done

cilium status --wait
cilium connectivity test

kubectl -n crafty-controller scale deployment crafty-controller --replicas=1
kubectl -n home-assistant scale deployment home-assistant --replicas=1
kubectl -n n8n scale deployment n8n --replicas=1

echo "Keep policyEnforcementMode=never for the 24-48 hour observation period."

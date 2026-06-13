#!/usr/bin/env bash
set -euo pipefail

if [[ "${CONFIRM_CILIUM_ROLLBACK:-}" != "yes" ]]; then
  echo "Set CONFIRM_CILIUM_ROLLBACK=yes during an approved rollback window." >&2
  exit 1
fi

nodes=()
while IFS= read -r node; do
  nodes+=("$node")
done < <(
  kubectl get nodes -o json |
    jq -r '.items[].status.addresses[] | select(.type == "InternalIP") | .address'
)
helm uninstall cilium -n kube-system || true
for node in "${nodes[@]}"; do
  talosctl --nodes "$node" patch machineconfig --patch @talos/patches/flannel.yaml
done

echo "Reboot nodes one at a time, wait for Flannel, then restart workloads."
echo "Use scripts/restore-pvc.sh only if storage verification fails."

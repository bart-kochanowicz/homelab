#!/usr/bin/env bash
set -euo pipefail

files=(
  "talos/controlplane.yaml"
  "talos/worker.yaml"
  "talos/talosconfig"
  "terraform/backend.tf"
  "terraform/variables.tfvars"
  "terraform/.terraform/terraform.tfstate"
  "${HOME}/.kube/config"
  "${HOME}/.talos/config"
)

failed=0
for file in "${files[@]}"; do
  [[ -e "${file}" ]] || continue
  mode="$(stat -f '%Lp' "${file}" 2>/dev/null || stat -c '%a' "${file}")"
  if (( (8#${mode} & 8#077) != 0 )); then
    printf 'insecure permissions %s on %s; expected no group/other access\n' \
      "${mode}" "${file}" >&2
    failed=1
  fi
done

exit "${failed}"

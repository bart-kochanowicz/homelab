#!/usr/bin/env bash
set -euo pipefail

files=(
  "talos/controlplane.yaml"
  "talos/worker.yaml"
  "talos/talosconfig"
  "terraform/variables.tfvars"
  "terraform/.terraform/terraform.tfstate"
  "terraform/unifi/.terraform/terraform.tfstate"
  "${HOME}/.kube/config"
  "${HOME}/.talos/config"
)

shopt -s nullglob
files+=(.secrets/unifi .secrets/unifi/*)

failed=0
for file in "${files[@]}"; do
  [[ -e "${file}" ]] || continue
  if [[ $(uname -s) == Darwin ]]; then
    mode="$(stat -f '%Lp' "${file}")"
  else
    mode="$(stat -c '%a' "${file}")"
  fi
  if (( (8#${mode} & 8#077) != 0 )); then
    printf 'insecure permissions %s on %s; expected no group/other access\n' \
      "${mode}" "${file}" >&2
    failed=1
  fi
done

exit "${failed}"

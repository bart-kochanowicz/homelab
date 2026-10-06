# Agent guide

This repository declares the desired homelab state. Keep migration history,
rollout stages, work logs, and planning material out of tracked configuration
and documentation. Document operational commands and non-obvious constraints.

## Layout

- `apps/`: Kubernetes applications registered through the ArgoCD ApplicationSet.
- `system/`: platform manifests, Helm charts, and local ArgoCD bootstrap.
- `talos/patches/`: Talos CNI configuration; generated machine configs are ignored.
- `terraform/`: Cloudflare R2; `terraform/unifi/`: UniFi LAN configuration.
- `infra/ansible/`: Houston's Garage backend, Terraform CLI, and private runner.
- `infra/unifi/`: network architecture and WAN operations.

## Checks

Run `make validate` for Terraform format/validation/tests, YAML, ShellCheck,
Kustomize, Helm, Kubernetes schemas, security scans, and secret detection.
Required tools are listed in `aqua.yaml`; yamllint is installed separately.
Use `make -C system bootstrap` for ArgoCD and `bootstrap-cilium` for Cilium.
These commands change the cluster; validation does not deploy resources.

## Conventions

- YAML: two-space indentation; explicit namespaces and consistent labels.
- Kubernetes: stable APIs, lowercase hyphenated names, `kustomization.yaml`.
- Terraform: run `terraform fmt -recursive`; use lowercase underscore names
  and descriptions for variables and outputs; mark secrets sensitive.
- Ansible: idempotent tasks and handlers; preserve explicit failure handling.
- Update relevant operational documentation when changing a component.

## Constraints

- Application endpoints are private. Do not publish them through Cloudflare Tunnel.
- Cilium is bootstrap-managed; network policies require manual ArgoCD sync.
- Changes in `system/argocd/` require bootstrap or manual sync.
- Preserve namespace/PVC deletion safeguards, backup checks, and failure recovery.
- Terraform state is remote in Garage; review a plan before applying it.
- Respect `KUBECONFIG` (default `~/.kube/config`); require Kubernetes v1.25+.
- Destructive cleanup and in-place restores require explicit confirmation.
- Never commit plaintext secrets, state, `.tfvars`, or generated Talos configs.
  Use SealedSecrets and ignored local files; keep examples free of credentials.
- Keep provider lock files tracked; do not delete them to work around errors.

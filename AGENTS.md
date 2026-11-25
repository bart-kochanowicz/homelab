# Agent guide

This repository declares the desired homelab state. Keep migration history,
rollout stages and work logs out of tracked configuration and documentation.
Plans live in an OpenSpec change folder on their branch or in the ignored
`thoughts/`. Document operational commands and non-obvious constraints.

## Layout

- `apps/`: Kubernetes applications registered through the ArgoCD ApplicationSet.
- `system/`: platform manifests, Helm charts, and local ArgoCD bootstrap.
- `talos/patches/`: Talos CNI configuration; generated machine configs are ignored.
- `terraform/cloudflare/`: Cloudflare R2 and DNS; `terraform/unifi/`: UniFi LAN configuration.
- `terraform/modules/`: reusable Terraform modules; shared backend settings and
  operational guides live directly in `terraform/`.
- `infra/ansible/`: Houston's Garage backend, Terraform CLI, and private runner.
- `infra/unifi/`: network architecture and WAN operations.
- `openspec/specs/`: what the homelab guarantees, one folder per capability.
- `.agents/skills/`: agent skills; `.claude/skills/` holds symlinks to them.
  Copied skills are listed in `.agents/skills/THIRD_PARTY.md`.
- `.claude/`: Claude Code settings, hooks and the `verifier` and `reviewer`
  subagents; `REVIEW.md` is the review policy.

Worktrees share the main checkout's ignored local files listed in
`.worktreeinclude`. `scripts/worktree-env.sh` links them; T3 runs it
when it creates a worktree. Run it manually in older worktrees, and add new
local inputs to `.worktreeinclude`.

## Checks

Run `make validate` for Terraform format/validation/tests, YAML, ShellCheck,
Kustomize, Helm, Kubernetes schemas, security scans, and secret detection.
Required tools are listed in `aqua.yaml`; yamllint is installed separately.
Python tests use `uv run --locked`; run `make validate-python` for Pyright type
checks and Ruff lint/format checks, or `make format-python` to fix imports and
formatting.
`make validate-openspec` checks specs and changes with the OpenSpec CLI
version pinned in the `Makefile`.
Use `make -C system bootstrap` for ArgoCD and `bootstrap-cilium` for Cilium.
These commands change the cluster; validation does not deploy resources.
Bare `make` runs bootstrap too.

## Workflow

- A change that adds or alters a guarantee in `openspec/specs/` starts with
  the `openspec-propose` skill. Implement it with `openspec-apply-change`, then
  run `openspec-archive-change` before merge: CI fails while a folder remains
  in `openspec/changes/`. Fixes and updates that keep every spec true skip it.
- Before saying a change is done, run the `verifier` subagent or
  `make validate`. Before a pull request, run the `reviewer` subagent.
- After merge, list the manual syncs, plans and runs the change needs
  (`platform-sync` skill).
- `.claude/hooks/guard.py` denies private files and Terraform applies, and asks
  before commands that change the cluster, state or Houston. Extend it and
  `tests/agents/` when a new private path or live command appears.
- When an agent repeats a mistake, add the correction to this file.

## Conventions

- Group Python tests by component; keep shared setup in package-local `support.py`.
- YAML: two-space indentation; explicit namespaces and consistent labels.
- Kubernetes: stable APIs, lowercase hyphenated names, `kustomization.yaml`.
- Terraform: run `terraform fmt -recursive`; use lowercase underscore names
  and descriptions for variables and outputs; mark secrets sensitive.
  Put deployable roots in `terraform/<name>/`, each with its own backend/state,
  and reusable modules in `terraform/modules/<name>/` without backend blocks.
  Do not put root configuration directly in `terraform/`.
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

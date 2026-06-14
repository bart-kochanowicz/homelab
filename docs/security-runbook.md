# Security Operations Runbook

## Bootstrap Order

1. Generate Talos machine configuration with `talos/patches/cilium.yaml`.
2. Bootstrap Talos and wait for the Kubernetes API through KubePrism.
3. Run `make -C system bootstrap-cilium`.
4. Verify `cilium status --wait`.
5. Run `make -C system bootstrap`.
6. Verify ArgoCD applications, cert-manager, sealed-secrets, storage, and monitoring.

Cilium is intentionally bootstrap-managed. Do not add it to the ArgoCD
ApplicationSet because loss of the CNI also removes ArgoCD's ability to repair it.

## GitHub SSO

The GitHub OAuth application uses:

- Homepage: `https://argocd.thecavespace.com`
- Callback: `https://argocd.thecavespace.com/api/dex/callback`

ArgoCD Dex configuration is tracked in `system/argocd/argocd-cm.yaml`. The
OAuth credentials are stored only as ciphertext in the patching SealedSecret at
`system/argocd/argocd-sso-sealed-secret.yaml`. The Helm bootstrap annotates the
existing `argocd-secret` for patching so the controller adds only the OAuth keys
without replacing Helm-managed credentials.

To rotate the OAuth credentials, export the replacement values and regenerate
the SealedSecret:

```bash
export GITHUB_OAUTH_CLIENT_ID=...
export GITHUB_OAUTH_CLIENT_SECRET=...
./scripts/generate-argocd-sso-secret.sh
```

After ArgoCD syncs the SSO configuration, verify:

1. `bart-kochanowicz` can log in through GitHub and use the UI and CLI.
2. A second GitHub identity receives no ArgoCD permissions.
3. Cloudflare Access still protects the public endpoint.
4. Cluster-admin access can temporarily restore the local account for recovery.

Cloudflare Access protects the ArgoCD UI and API. Two path-specific Access
applications bypass authentication only for Dex's public OIDC discovery
document and signing keys, which `argocd-server` must fetch to verify login
tokens. Do not broaden this bypass to other ArgoCD or Dex paths.

Local admin is disabled after the SSO and RBAC tests. Recovery requires
temporary cluster-admin access to set `admin.enabled: "true"` in `argocd-cm`
and restart `argocd-server`. Restore `admin.enabled: "false"` after recovery.

Commit only the regenerated SealedSecret ciphertext. Never commit OAuth
plaintext.

## Internal CA

The offline CA private key is stored under `.secrets/` with mode `0600`; only its
sealed form is tracked. Back up the private key separately from the repository.
The `argocd-server-tls` certificate renews automatically through cert-manager.
Cloudflared mounts the public CA and verifies
`argocd-server.argocd.svc.cluster.local`.

To rotate the CA:

1. Generate a new offline key and certificate.
2. Seal the TLS secret for the `cert-manager` namespace.
3. Update `system/cloudflared/root-ca-configmap.yaml`.
4. Commit both changes and verify certificate issuance before removing old trust.

## PVC Backup And Restore

Application namespaces and protected PVCs use ArgoCD
`Prune=false,Delete=false`. Generated Applications also preserve resources when
their source directory is removed. Do not remove these safeguards during
ApplicationSet or namespace ownership changes; deleting a Namespace cascades to
its PVCs and workloads.

Configure an encrypted workstation restic repository:

```bash
export RESTIC_REPOSITORY="/Volumes/SanDisk/Backups/homelab-restic"
export RESTIC_PASSWORD_FILE="$HOME/.config/restic/homelab-password"
export RESTORE_TEST_DIR="/Volumes/SanDisk/Backups/homelab-restore-tests"
./scripts/backup-pvcs.sh
```

The local repository path must be absolute. In particular, keep the leading
slash in `/Volumes`; `Volumes/...` creates a repository inside the Git checkout.
The script scales down Crafty, Home Assistant, and n8n one at a time, mounts each
PVC read-only in a temporary pod, retries transient stream failures, confirms
that each snapshot was finalized, runs `restic check`, restores replicas, and
writes `.backups/last-successful-backup`. It also updates the
`workstation-pvc-backup-success` or `workstation-pvc-backup-failure` Lease in
the `monitoring` namespace. Prometheus alerts when the latest attempt failed,
no success has been recorded, or the latest success is over seven days old.
The previous successful local marker is retained when a later backup fails.
Prometheus data is intentionally disposable.

Run this backup at least weekly. After the first run, verify the timestamp:

```bash
kubectl -n monitoring get leases \
  workstation-pvc-backup-success workstation-pvc-backup-failure
```

The failure Lease may be absent until the first failed attempt. If Kubernetes
is unreachable, the script cannot update the failure Lease and prints a
warning; the stale-backup alert remains the fallback signal.

Test restoring every PVC to the workstation or external disk without changing
Kubernetes:

```bash
./scripts/restore-pvc.sh crafty-controller crafty-controller crafty-data
./scripts/restore-pvc.sh home-assistant home-assistant home-assistant-config
./scripts/restore-pvc.sh n8n n8n n8n-data
```

Inspect a known test file under each printed restore directory. The global
`.backups/last-successful-restore-test` marker is written only after all three
restore tests succeed. The migration refuses to run without both backup and
restore-test markers.

An actual disaster recovery overwrite is deliberately separate:

```bash
CONFIRM_IN_PLACE_RESTORE=yes ./scripts/restore-pvc.sh --in-place \
  n8n n8n n8n-data
```

The script verifies the snapshot and archive path before scaling the deployment.

## Cilium Migration

First run the non-destructive preflight:

```bash
make -C system cilium-preflight
```

During an approved maintenance window:

1. Run and restore-test `./scripts/backup-pvcs.sh`.
2. Pre-pull Cilium images on both nodes.
3. Confirm out-of-band Talos access to both nodes.
4. Run `make -C system cilium-migrate`.
5. Verify `cilium status`, `cilium connectivity test`, DNS, ClusterIP, NodePort,
   Hubble Relay, ArgoCD, cloudflared, and all applications.
6. Leave `policyEnforcementMode: never` for 24-48 hours while reviewing flows.
7. Add `network-policies.yaml` back to `system/argocd/kustomization.yaml`, merge
   it, and manually sync the `network-policies` Application.
8. Confirm all policies are present before applying the tracked Cilium values
   with `make -C system bootstrap-cilium`.

The migration deliberately keeps kube-proxy and the existing pod/service CIDRs.
It is a maintenance cutover, not a dual-overlay live migration.

Rollback:

```bash
make -C system cilium-rollback
```

Then reboot nodes one at a time, wait for Flannel, recycle workloads, verify
services, and use the restic restore command only if data verification fails.

## Network Enforcement

`system/argocd/network-policies.yaml` intentionally has no automated sync.
After changing its rules, manually sync it before applying Cilium configuration
with `policyEnforcementMode: default`. Run negative tests for cross-namespace
traffic and unauthorized ingress immediately after enforcement.

Home Assistant uses host networking, so cloudflared reaches identity `host` or
`remote-node` rather than a namespaced pod identity. The dedicated Cilium policy
allows only those identities on TCP `8123`; do not replace it with unrestricted
LAN egress.

The Cilium host policy at `system/network-policies/host-firewall.yaml` is
managed by the manually synced `network-policies` Application. Before changing
it, enable `PolicyAuditMode` on each Cilium host endpoint, review Hubble host
flows, and verify required traffic. Audit mode is not persistent across Cilium
agent restarts, so either finish the review and enforce the policy or remove the
live policy before restarting an agent.

The current allowlist was reviewed on June 14, 2026. It preserves node-internal
traffic, cluster workload access to the Kubernetes API on TCP `6443`, CoreDNS
access to the node-local resolver, Hubble Relay access to agent peers,
monitoring scrapes, Cloudflare access to Home Assistant, management LAN access,
Home Assistant discovery, and public Minecraft TCP `30000`.

Required preserved paths:

- Cloudflared to ArgoCD, Crafty, Home Assistant, Grafana, and n8n.
- Public n8n webhook host paths through the tunnel.
- Public Minecraft TCP `30000`.
- Home Assistant LAN discovery and TCP `8123`.
- Kubernetes and Talos management from the management LAN.

## Retained Volumes

The local-path StorageClass uses `Retain`. Deleting a PVC leaves its PV and data
directory intact. To permanently remove one:

1. Confirm a successful backup.
2. Delete the PVC.
3. Inspect the retained PV and its node/path.
4. Delete the PV object.
5. Remove the directory on that node through an approved Talos maintenance path.

New directories are mode `0770`; n8n receives UID/GID `1000:1000`, while the
documented root-running workloads receive `0:0`.

## Secret And Credential Rotation

- Run `./scripts/check-sensitive-permissions.sh` before maintenance.
- Rotate Cloudflare, GitHub OAuth, n8n, Sealed Secrets, and CA credentials
  independently.
- Regenerate SealedSecrets; never edit ciphertext manually.
- Run `gitleaks git --log-opts=--all` after every rotation.
- Treat Terraform state as secret even when outputs are marked sensitive.

## GitHub Branch Protection

After the `Validate` workflow has succeeded on `main`, enable the required check
and pull-request protection:

```bash
CONFIRM_BRANCH_PROTECTION=yes ./scripts/configure-branch-protection.sh
```

This requires pull requests with zero approvals, resolved conversations, an
up-to-date successful `validate` check, linear history, and blocks force pushes
and branch deletion.

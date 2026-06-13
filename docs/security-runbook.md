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

Create a GitHub OAuth application with:

- Homepage: `https://argocd.thecavespace.com`
- Callback: `https://argocd.thecavespace.com/api/dex/callback`

Export the client values and generate the patching SealedSecret:

```bash
export GITHUB_OAUTH_CLIENT_ID=...
export GITHUB_OAUTH_CLIENT_SECRET=...
./scripts/generate-argocd-sso-secret.sh
```

Add `system/argocd/argocd-sso-sealed-secret.yaml` and merge the contents of
`system/argocd/argocd-sso.patch.example.yaml` into `argocd-cm.yaml`. Verify:

1. `bart-kochanowicz` can log in through GitHub and use the UI and CLI.
2. A second GitHub identity receives no ArgoCD permissions.
3. Cloudflare Access still protects the public endpoint.
4. The local admin login still works as an emergency fallback.

Only after those checks, apply
`system/argocd/argocd-disable-admin.patch.example.yaml` in a separate commit.
Recovery requires temporary cluster-admin access to set `admin.enabled: "true"`
and restart `argocd-server`.

Rotate the OAuth secret by rerunning the generator and committing only the
SealedSecret ciphertext. Never commit OAuth plaintext.

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
writes `.backups/last-successful-backup`. Prometheus data is intentionally
disposable.

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
   it, and verify the explicit allow rules before enabling policy enforcement.

The migration deliberately keeps kube-proxy and the existing pod/service CIDRs.
It is a maintenance cutover, not a dual-overlay live migration.

Rollback:

```bash
make -C system cilium-rollback
```

Then reboot nodes one at a time, wait for Flannel, recycle workloads, verify
services, and use the restic restore command only if data verification fails.

## Network Enforcement

`system/argocd/network-policies.yaml` has no automated sync. After the Cilium
observation period, manually sync it and run negative tests for cross-namespace
traffic and unauthorized ingress.

The Cilium host policy at `system/cilium/policies/host-firewall.yaml` is staged.
Review at least 48 hours of Hubble host flows before applying it and changing
policy enforcement from audit/disabled mode.

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

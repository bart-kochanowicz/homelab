# Security operations

## Configuration

- Cilium enforces pod policies and the host firewall on both nodes.
- The `network-policies` ArgoCD Application requires manual sync.
- ArgoCD local admin is disabled; GitHub SSO grants admin to `bart-kochanowicz`.
- Application UIs and webhooks use private access.
- Application PVCs have encrypted restic backups; Kubernetes Leases report results.
- Local-path volumes use `Retain`, mode `0770`, and workload-specific ownership.

Compatibility exceptions are listed in [exception-register.md](exception-register.md).

## Bootstrap

1. Generate Talos machine configuration with `talos/patches/cilium.yaml`.
2. Bootstrap Talos and wait for the Kubernetes API through KubePrism.
3. Run `make -C system bootstrap-cilium`, then `cilium status --wait`.
4. Run `make -C system bootstrap`.
5. Verify ArgoCD applications, certificates, storage, monitoring, and network policies.

Cilium is managed outside ArgoCD so network recovery does not depend on GitOps.

## Private application access

| Application | URL |
| --- | --- |
| ArgoCD | `https://argocd.thecavespace.com` |
| n8n editor | `https://n8n.thecavespace.com` |
| n8n webhooks | `https://n8n-webhook.thecavespace.com/` |

ArgoCD and n8n use `ClusterIP` Services. Private DNS must resolve these names to
a LAN HTTPS entry point with routes to those Services. DNS, TLS, and the LAN
entry point are configured outside the application manifests. Clients must
trust the issuer, and ArgoCD server pods must resolve and reach the ArgoCD URL
for SSO. Keep Kubernetes API access available for recovery.

Verify DNS, HTTPS, GitHub login, n8n login, and a disposable webhook from an
authorized LAN client. For access failures, check private DNS and HTTPS routes.

## GitHub SSO

GitHub OAuth uses homepage `https://argocd.thecavespace.com` and callback
`https://argocd.thecavespace.com/api/dex/callback`. Dex and RBAC configuration
live in `system/argocd/`. The SSO SealedSecret patches OAuth keys into the
Helm-managed `argocd-secret` without replacing its other credentials.

Rotate credentials with:

```bash
export GITHUB_OAUTH_CLIENT_ID=...
export GITHUB_OAUTH_CLIENT_SECRET=...
./scripts/generate-argocd-sso-secret.sh
```

Commit the ciphertext, sync ArgoCD, and verify that `bart-kochanowicz` can use
the UI/CLI while a second GitHub identity receives no permissions. The private
HTTPS route must serve Dex's OIDC discovery document and signing keys.

For local-admin recovery, use cluster-admin access to set `admin.enabled: "true"`
in `argocd-cm` and restart `argocd-server`. Restore `admin.enabled: "false"`
after recovery.

## Internal CA

Keep the offline CA key under `.secrets/` with mode `0600` and a separate backup.
Only its sealed form is tracked. Cert-manager renews `argocd-server-tls`;
private clients must trust the public CA.

To rotate the CA, generate a new key/certificate, seal the TLS secret for
`cert-manager`, distribute the public CA, and commit the SealedSecret. Verify
certificate issuance before removing the old trust.

## PVC backup and restore

Namespaces and PVCs use ArgoCD `Prune=false,Delete=false`; generated
Applications preserve resources when their source directory is removed.
Preserve these safeguards: Namespace deletion cascades to PVCs and workloads.

```bash
export RESTIC_REPOSITORY="/Volumes/SanDisk/Backups/homelab-restic"
export RESTIC_PASSWORD_FILE="$HOME/.config/restic/homelab-password"
export RESTORE_TEST_DIR="/Volumes/SanDisk/Backups/homelab-restore-tests"
./scripts/backup-pvcs.sh
```

Local restic paths must be absolute. Backup stops each application in turn,
streams its PVC read-only, verifies snapshots with `restic check`, and restores
replicas. Prometheus data is disposable. The script records the last success in
`.backups/last-successful-backup` and updates monitoring Leases:

```bash
kubectl -n monitoring get leases \
  workstation-pvc-backup-success workstation-pvc-backup-failure
```

Alerts cover failed attempts, missing success, and successes older than seven
days. The failure Lease exists only after a failed attempt. If Kubernetes is
unreachable, Lease updates fail and the stale-backup alert remains the fallback.
A failed backup preserves the previous local success marker.

Test restores without changing Kubernetes:

```bash
./scripts/restore-pvc.sh crafty-controller crafty-controller crafty-data
./scripts/restore-pvc.sh home-assistant home-assistant home-assistant-config
./scripts/restore-pvc.sh n8n n8n n8n-data
```

Inspect a known file in each restore directory.

To overwrite a live PVC during recovery:

```bash
CONFIRM_IN_PLACE_RESTORE=yes ./scripts/restore-pvc.sh --in-place \
  n8n n8n n8n-data
```

The script verifies the snapshot and archive path before stopping the workload.

## Network policies

Manually sync `network-policies` after rule changes and test required access
and denied cross-namespace traffic. Home Assistant host-network traffic is
controlled by the Cilium host firewall.

Before changing the host policy, enable `PolicyAuditMode` on each Cilium host
endpoint and review Hubble flows. Audit mode resets on agent restart; finish
the review and enforce the policy, or remove the live policy before restarting.
The allowlist preserves:

- Node-internal traffic, pod access to the API on TCP `6443`, and CoreDNS upstream DNS.
- Hubble peer traffic and monitoring scrapes.
- Kubernetes/Talos access from the management LAN.
- Home Assistant LAN discovery and TCP `8123`.
- Public Minecraft TCP `30000`.

## Retained volumes

Deleting a PVC leaves its PV and node data intact. To remove retained data,
confirm a successful backup, delete the PVC, inspect the PV's node/path,
delete the PV, then remove the directory through Talos maintenance access.
New directories use mode `0770`; n8n uses `1000:1000`, and root-running
workloads use `0:0`.

## Credentials and branch protection

Keep credential/state files mode `0600` in private `0700` directories. Rotate
Cloudflare, OAuth, n8n, Sealed Secrets, and CA credentials independently.
Regenerate SealedSecrets and run `gitleaks git --log-opts=--all` after rotation.
Treat Terraform state as secret even when outputs are marked sensitive.

Configure branch protection after a successful `Validate` run on `main`:

```bash
CONFIRM_BRANCH_PROTECTION=yes ./scripts/configure-branch-protection.sh
```

Protection requires PRs, resolved conversations, an up-to-date `validate` check,
and linear history. Required approvals are zero; force pushes and branch
deletion are blocked.

## Maintenance

| Frequency | Task |
| --- | --- |
| Weekly | Back up PVCs, inspect the success Lease, and review alerts. |
| Monthly | Review Crafty TLS compatibility, certificate expiry, image scans, and Renovate PRs. |
| Quarterly | Review security exceptions, test every PVC restore, and rehearse SSO recovery. |
| After security changes | Run `make validate`, check ArgoCD health, and test allowed/denied connectivity. |

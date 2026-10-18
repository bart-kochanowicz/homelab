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
It replaces kube-proxy for Kubernetes Services and reaches the API through
KubePrism at `localhost:7445`. Keep `bpf.hostLegacyRouting: true` while CoreDNS
forwards to Talos host DNS.

Talos `cluster.proxy.disabled: true` prevents kube-proxy recreation but does not
delete an existing DaemonSet or its node rules. Any removal requires a verified
Cilium replacement and an approved maintenance window. Recovery requires
restoring Talos proxy configuration and working kube-proxy service handling
before disabling Cilium replacement; a Helm rollback alone is insufficient.

## Gateway API definitions

Sync `argocd-bootstrap` to register the dedicated `gateway-api-crds` Application,
then sync `gateway-api-crds` manually. It owns the pinned standard CRDs using
server-side apply; pruning and deletion are disabled for those CRDs. Keep Helm
and other Applications from owning the same definitions.

`make validate-gateway-api` derives strict JSON schemas from those exact CRDs
and validates rendered Gateway API resources without skipping missing schemas.
Kubernetes server validation also checks CEL rules when resources are submitted.

## Private GitOps configuration

Public manifests contain reserved example domains. Production ArgoCD and
application overlays live in the private `homelab-config` repository; ACME
issuers and frontend Certificates are defined there. ArgoCD uses a repository-
specific read-only deploy key sealed in `homelab-config-repository`.

Private overlays pin the public bases to a commit. Update those references
when deploying changes from this repository. Validate both the public bases
and private overlays before syncing. Bootstrap needs the repository
SealedSecret and exact AppProject source grants before the private sources
can be read. Keep existing Application names and deletion safeguards when
changing their sources.

## Private application access

The following URLs are examples. Actual endpoints and OAuth callbacks come
from private overlays; do not commit their values here.

| Application | URL |
| --- | --- |
| ArgoCD | `https://argocd.example.com` |
| n8n editor | `https://n8n.example.com` |
| n8n webhooks | `https://n8n-webhook.example.com/` |

ArgoCD and n8n use `ClusterIP` Services. Private DNS must resolve these names to
a LAN HTTPS entry point with routes to those Services. DNS, TLS, and the LAN
entry point are configured outside the application manifests. Clients must
trust the issuer, and ArgoCD server pods must resolve and reach the ArgoCD URL
for SSO. Keep Kubernetes API access available for recovery.

Verify DNS, HTTPS, GitHub login, n8n login, and a disposable webhook from an
authorized LAN client. For access failures, check private DNS and HTTPS routes.

## GitHub SSO

GitHub OAuth uses homepage `https://argocd.example.com` and callback
`https://argocd.example.com/api/dex/callback`. Dex and RBAC configuration
use public bases in `system/argocd/` and private endpoint overrides. The SSO
SealedSecret patches OAuth keys into the
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

## Frontend certificates

`cert-manager-acme` requires manual ArgoCD sync. It owns the DNS-01 issuers,
Cloudflare SealedSecret, and separate wildcard Certificates in `private-home`
and `private-admin`. Its resources are protected from pruning and deletion.
Sync the issuers and SealedSecret selectively, validate issuance and renewal
with a temporary Certificate using `letsencrypt-staging`, then sync the
production Certificates. Staging certificates are not browser-trusted.

The `cloudflare-dns01-token` Secret belongs in `cert-manager`, the controller's
cluster resource namespace. DNS Edit and Zone Read permissions must be
restricted to the configured DNS zone. This token is shared with Terraform/R2;
coordinate rotation with its other consumers. Keep plaintext credentials in
ignored files with mode `0600`. Seal a replacement token saved without a
trailing newline in `.secrets/cloudflare-dns01-token` with
`PRIVATE_CONFIG_DIR` pointing to your private checkout:

```bash
kubectl create secret generic cloudflare-dns01-token --namespace cert-manager \
  --from-file=api-token=.secrets/cloudflare-dns01-token --dry-run=client -o json | \
  kubeseal --controller-name=sealed-secrets-controller \
    --controller-namespace=sealed-secrets --scope strict --format yaml \
    > "$PRIVATE_CONFIG_DIR/cert-manager-acme/sealed-cloudflare-token.yaml"
```

Commit the ciphertext in the private configuration repository and sync
`cert-manager-acme`. Its solver is limited to the configured DNS zone; the Cloudflare permission covers all DNS record types
in that zone. Cert-manager owns transient challenge TXT records. Preserve
public TXT/SOA resolution when configuring private DNS; no inbound WAN ports
or public A/AAAA/CNAME records are needed for private services.

Each gateway has its own TLS Secret and rotating ECDSA key. Only the wildcard
appears in Certificate SANs, keeping private service names out of public
Certificate Transparency logs. The wildcard does not authorize routes or DNS
records. Renew and inspect Certificates with the pinned `cmctl` tool:

```bash
cmctl status certificate private-home-wildcard --namespace private-home
cmctl renew private-home-wildcard --namespace private-home
cmctl status certificate private-admin-wildcard --namespace private-admin
```

Confirm a new revision, `Ready=True`, and the new certificate served by HTTPS
listeners after renewal. Cert-manager schedules renewal from the issued
certificate's actual lifetime; monitoring alerts before expiry. ACME account
keys are generated in-cluster, separately for staging and production.
`make validate-cert-manager` validates resources against CRDs from the pinned
Helm chart without skipping missing schemas.

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

Sync `network-policies` manually with pruning from a verified Admin connection.
Test required access and denied traffic using fresh connections and Hubble verdicts.

| Source | Access |
| --- | --- |
| Admin `10.0.80.0/24` | Node administration, Crafty TCP `8443`, Minecraft TCP `30000`, n8n TCP `5678` |
| Home `10.0.40.0/24` | Home Assistant TCP `8123`, Minecraft TCP `30000` |
| n8n | Home Assistant on local or remote nodes, TCP `8123` |

Home Assistant uses `hostNetwork`; its namespace policies cannot isolate it.
Host rules apply to every process listening on the allowed node ports. n8n uses
Cilium host/node identities for this connection; default Cilium CIDR matching and
namespace selectors do not select host-network workloads. Host egress remains unrestricted.

Minecraft uses `externalTrafficPolicy: Local` to preserve client IPs for pod
policy enforcement. Connect to a node running the Crafty pod; other nodes do not
forward this NodePort. UI Services remain `ClusterIP` and require private routing
or authenticated port-forwarding.

Before changing the host policy, enable `PolicyAuditMode` on each Cilium host
endpoint and review Hubble flows. Audit mode resets on agent restart; finish
the review and enforce the policy, or remove the live policy before restarting.
The allowlist also preserves node-internal traffic, pod access to the API on TCP
`6443`, CoreDNS upstream DNS, Hubble peer traffic and monitoring scrapes.

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

# Cavespace Network Preflight and Recovery

Use with the [architecture plan](../../../thoughts/shared/plans/2026-10-04-cavespace-unifi-baseline.md)
and [current inventory](network-inventory.md). PR 01 collects evidence only.
Each later PR must be merged, deployed and verified before the next is opened.

## Read-only preflight

1. In UniFi, record model/version, LAN/DHCP/IPv6, WLAN security/isolation,
   reservations, static/VPN routes, rules, forwarding and discovery settings.
   Preserve full device port overrides and native/allowed-tag lists privately.
   Record identities and physical cable labels before choosing import targets.
2. On the operator workstation, record connected/VPN routes and compare all
   proposed LAN, VPN and LoadBalancer ranges with employer routes and live
   Kubernetes pod/service CIDRs. Do not infer CIDRs from old defaults.
3. From Houston, check host routes, filesystem, services and the controller's
   trusted TLS/API path without printing credentials or Terraform state.
   Document a private credential procedure; do not create credentials in this PR.
4. Identify both Talos nodes through authenticated API or local console.
   Once a verified endpoint is known, inspect node roles/versions, health,
   pod CIDRs, actual service CIDRs, HA scheduling, PV affinity and backup Leases.
   A timeout/refusal is an unresolved check, not evidence of a firewall deny.

Example read-only queries, after restoring a verified Kubernetes context:

```bash
ssh houston-01 'hostname; ip -brief address; ip route; findmnt /srv/terraform'
kubectl --context=homelab-prod get nodes -o wide
kubectl --context=homelab-prod get nodes \
  -o custom-columns=NAME:.metadata.name,POD_CIDRS:.spec.podCIDRs
kubectl --context=homelab-prod -n home-assistant get pods -o wide
kubectl --context=homelab-prod -n home-assistant get pvc
kubectl --context=homelab-prod get pv \
  -o custom-columns=NAME:.metadata.name,CLAIM:.spec.claimRef.name,NAMESPACE:.spec.claimRef.namespace,AFFINITY:.spec.nodeAffinity,PATH:.spec.hostPath.path
kubectl --context=homelab-prod -n monitoring get leases \
  workstation-pvc-backup-success workstation-pvc-backup-failure
```

The kubeconfig's current endpoint is unverified. Substitute only an identified,
certificate-valid endpoint; do not disable TLS verification. Query Talos with
the existing private talosconfig and explicit verified `--endpoints` / `--nodes`.
Keep machine configurations, certificates, raw exports and detailed output
private. Record only sanitized conclusions in the verification ledger.

## Recovery prerequisites

Before closing PR 01, confirm an independent wired operator path, local
gateway access, local console/recovery access to both nodes, and credentials
available without cluster-hosted DNS. Record a port/cable map and each port's
known-good settings. Today recovery uses the verified legacy network; create
and test the dedicated Admin VLAN 80 recovery port in PR 06 before restricting
access or changing management addressing. No such port is proven yet.

Keep backups outside Git with owner-only access and an independent recoverable
copy. Record timestamps, installed versions, integrity checks and a private
receipt reference; never the credential-bearing payload.

| Recovery material | Required evidence |
| --- | --- |
| UniFi | Current configuration backup, device identities, credentials and documented restore path; rehearsal status recorded |
| LEOX / WAN | Existing private GPON parameters, route/SNAT baseline and known-working operator access; no reinstall |
| Talos / etcd | Private machine secrets/configs and fresh control-plane snapshot; recovery procedure matched to installed Talos version |
| Application PVCs | Backup of each protected claim, actual PV node/path/affinity and successful non-destructive restore verification |
| Terraform | Correct backend key/lineage and verified private snapshot/restore procedure before stateful operations |

The [security runbook](../../../docs/security-runbook.md#pvc-backup-and-restore)
contains PVC backup and restore procedures. Its backup script scales workloads
down, so it is not part of this read-only inventory. Schedule it separately
after API recovery. Check historical addresses before following older commands.
Etcd snapshots do not back up PVC data. Exporting a backup does not prove restore.
State procedures are in [BACKEND.md](../../../terraform/BACKEND.md) and
[R2_BACKUP.md](../../../terraform/R2_BACKUP.md); PR 02 adds isolated UniFi state.

## Applying later stages

Record the PR, merged commit, operator, deployment boundary, previous settings,
backup receipt and test results in the [ledger](../../../docs/security-verification.md).
Recheck Internet, WAN/LEOX, wired administration, Houston API access, devices,
cluster health and application data after every relevant change.

- Keep Terraform plan/review/apply serialized on Houston. Its lock covers one
  command; it does not reserve the whole operator sequence.
- Prepare allowed VLAN tags end-to-end before any management cutover.
  Switches use tagged Management 90 with a different native network; the AP
  uses native Management 90 without a matching Network Override.
- Retire legacy untagged WLANs before changing AP native management. Move one
  device at a time and wait for online/reprovision verification.
- Stop idle runner jobs before Houston's migration; an independent wired
  operator performs its cutover. Preserve Garage storage, keys and loopback.
- Move the worker before the control plane. Preserve node identities, disks,
  PVC affinity and CIDRs. Prepare API DNS/TLS before either address cutover.

For negative tests, use known-listening targets and fresh sessions. Record
source VLAN/address and correlated gateway/Cilium evidence. Include IPv6 and
Gateway link-local administration, WAN-side ONT access, PPSK placement and
actual routed Guest-to-Home AirPlay. Discovery and successful playback are
separate checks; same-VLAN peers are outside inter-zone firewall enforcement.

## Failure and rollback

Stop the current stage on lost administration, WAN, device adoption, API or
data access. Use the independently verified wired/local path to restore only
the affected device's recorded address/native/tags/profile or last verified
LAN rules, then repeat the stage checks. Do not reopen blanket legacy trust.
Restore an old SSID only with its verified legacy network, never Management 90.

Do not factory-reset, rebootstrap, delete PVCs or restore etcd as routine
network rollback. Restore Terraform state only after actual state loss or
corruption; it is not a gateway configuration backup. Keep WAN/PPPoE, `eth6`,
GPON identities and the LEOX runtime script outside these changes. The WAN
guide's /24 and script's /32 discrepancy is recorded in the inventory and
must not trigger an unplanned repair.

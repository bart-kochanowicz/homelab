# Application backups

Houston stores encrypted restic archives on its ext4 SSD at
`/srv/terraform/backups/homelab-restic`. Daily copies start at 03:00:30
Europe/Warsaw and retain 7 daily, 4 weekly and 3 monthly versions per application.
Retention periods overlap; they are not 14 independent snapshots. Only snapshots
tagged `houston-managed` on host `houston-01` belong to this policy.

Home Assistant, n8n and Grafana are stopped one at a time.
ArgoCD denies synchronization of these applications and their backup
helpers from 03:00 to 03:30. A missing window, active sync or unexpected PVC user
aborts the copy. Application logs are excluded; Prometheus history is not backed up.

The `backup-svc` account uses a dedicated Kubernetes client certificate with only
`CN=houston-backup`, no organization/group fields. An operator issues and approves
it through the Kubernetes `kubernetes.io/kube-apiserver-client` CSR signer; use an
embedded kubeconfig for `https://10.0.70.11:6443`, user `houston-backup`, namespace
`monitoring`. It may read the three read-only helpers and scale their named
deployments, but cannot read Secrets, create Pods or alter GitOps settings.
Renew this certificate before expiry and reapply the
[Ansible configuration](../infra/ansible/README.md#application-backups).
Keep a separate offline copy of the restic password; losing it makes recovery impossible.

## Operations

On Houston:

```bash
systemctl list-timers homelab-backup.timer
journalctl -u homelab-backup.service -u homelab-backup-recovery.service
sudo systemctl start homelab-backup.service
```

A manual run uses the same 03:00:15–03:05 start window. Run through systemd so all
files belong to `backup-svc`. Scheduling has no catch-up after shutdown. Replica
counts are persisted before stopping an application; recovery runs after failures
and at boot, retaining its state until the original replicas are ready. Do not
delete state files to clear an error. The service's 20-minute budget includes
verification and retention; application copying has a shorter 15-minute budget.

For repository inspection and an isolated restore on Houston:

```bash
sudo -u backup-svc sh
set -a; . /etc/homelab-backup/environment; set +a
restic snapshots --host houston-01 --tag houston-managed
restic restore SNAPSHOT_ID --target /srv/terraform/backups/tmp/restore-check
tar -tf /srv/terraform/backups/tmp/restore-check/n8n/n8n-data.tar
exit
```

Use an explicit snapshot ID and a new restore directory. Extract the archive there
and check its database and application files before any live recovery. The scoped
backup identity cannot perform an in-place restore. Such restores need an operator,
an ArgoCD maintenance window and explicit approval; `restore-pvc.sh --in-place`
overlays files and does not remove stale data.

Every successful run checks repository metadata and one seventh of stored data;
all seven subsets are read across a week. Only verified three-application runs
update `monitoring/houston-pvc-backup-success`. A failure preserves the previous
success timestamp; missing API access is detected by the age alert after 36 hours.
Keep scheduling and pruning disabled until a timed backup, isolated restore and
retention dry-run pass. Existing MacBook archives are separate and remain intact.

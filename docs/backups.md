# Application backups

K8up backs up Home Assistant, n8n and Grafana daily at **03:00 Europe/Warsaw**.
Crafty/Minecraft and disposable Prometheus data are excluded. Repositories live on
Houston's SSD at `/srv/terraform/backups/restic/{home-assistant,n8n,monitoring}`.
Retention keeps 7 daily, 4 weekly and 3 monthly snapshots; pruning runs Sunday at
05:00. Sunday checks at 04:00 read and verify every stored data block.

Each backup mounts the application's PVC read-only, uses SQLite's online backup
command and prepares a tar archive containing the database and a `files.tar`
archive of the remaining files before streaming it to restic. Applications
keep running. Database copies are transactional; other files are copied during
normal operation and do not form an atomic application-wide snapshot. Preparation
uses at most 4 GiB of temporary node storage and does not change PVC ownership.

## Storage and credentials

The [Houston REST-server](../infra/ansible/README.md#application-backup-storage)
uses TLS and separate bcrypt credentials for each repository. Restic encrypts
contents with separate repository passwords. Its 90 GiB storage limit covers all
repositories together; it is an application limit, not a filesystem quota.
Houston accepts connections only from the cluster nodes and Houston itself. Backup jobs reach only
the Kubernetes API and this storage endpoint; preparation pods have no network access.

Strict SealedSecrets contain each namespace's `k8up-repo` credentials. Private
source files are under `.secrets/houston-restic/`; keep an independent protected
copy of repository passwords, TLS keys and the offline CA key. Losing a repository
password prevents recovery. `system/backups/ca.crt` is public trust material.
Renew the server certificate before expiry, preserving its IP SAN and distributing
new CA trust before a CA change.

Install CRDs before the operator. The operator chart skips Helm hooks because
its legacy cleanup hook removes old executor RBAC across namespaces. Sync backup
definitions only after storage and credentials are ready. All three ArgoCD backup
Applications require manual synchronization. Before enabling schedules, run one
backup and an isolated restore per application; review retention with restic's
`forget --dry-run` before allowing pruning.

## Inspect and restore

```bash
kubectl get schedules,backups,checks,prunes -A
kubectl -n n8n logs job/JOB_NAME
ssh houston-01 'journalctl -u restic-server.service --since today'
```

For an isolated n8n restore on the MacBook, select a snapshot belonging to a
**completed successful Backup**, not an unchecked `latest` snapshot:

Open an SSH tunnel in another terminal: `ssh -N -L 127.0.0.1:48444:10.0.70.10:8444 houston-01`.

```bash
export RESTIC_REPOSITORY=rest:https://127.0.0.1:48444/n8n/
export RESTIC_REST_USERNAME=n8n
export RESTIC_REST_PASSWORD="$(cat .secrets/houston-restic/n8n.http-password)"
export RESTIC_PASSWORD_FILE="$PWD/.secrets/houston-restic/n8n.repo-password"
umask 077
restore_dir=$(mktemp -d "${TMPDIR:-/tmp}/n8n-restore.XXXXXX")
restic --cacert system/backups/ca.crt snapshots
restic --cacert system/backups/ca.crt dump SNAPSHOT_ID /n8n-archive.tar > "$restore_dir/archive.tar"
mkdir "$restore_dir/data"
tar -xf "$restore_dir/archive.tar" -C "$restore_dir"
cp "$restore_dir/database.sqlite" "$restore_dir/data/"
tar -xf "$restore_dir/files.tar" -C "$restore_dir/data"
sqlite3 "$restore_dir/data/database.sqlite" 'PRAGMA integrity_check;'
unset RESTIC_REST_PASSWORD
```

Use the corresponding namespace and database for HA (`home-assistant_v2.db`) or
Grafana (`grafana.db`). Inspect configuration and test the application separately.
Restic integrity checks and successful job status do not replace restore tests.
An in-place restore requires explicit approval, an application stop and protection
from ArgoCD self-heal. Existing MacBook repositories remain readable with native
`restic snapshots`, `ls`, `dump` and `restore`; their paths and passwords are unchanged.

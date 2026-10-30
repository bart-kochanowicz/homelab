# Application backups

All schedules use **Europe/Warsaw**. Sources below are PVCs, with subdirectories
shown where only part of a claim is copied.

| Data | Source | Destination | Schedule | Retention |
| --- | --- | --- | --- | --- |
| Home Assistant | `home-assistant-data-nvme` | Houston / K8up | Daily 03:00 | 7 daily, 4 weekly, 3 monthly |
| n8n | `n8n-data-nvme` | Houston / K8up | Daily 03:00 | 7 daily, 4 weekly, 3 monthly |
| Grafana | `grafana-data-nvme` | Houston / K8up | Daily 03:00 | 7 daily, 4 weekly, 3 monthly |
| Crafty panel | `crafty-data-nvme`, `app-config/` | Houston / K8up | Monday 03:00 | 1 daily, 4 weekly |
| Minecraft ATM10 8.3 | `crafty-data-nvme`, `servers/<server-id>/` | Worker SATA / ZIP | Monday 03:00 | 4 latest archives |

`system/backups/values.yaml` selects the K8up sources. Each application uses its
namespace as the repository name under Houston's `/srv/terraform/backups/restic/`.
Restic retention buckets can overlap; Crafty's daily and weekly settings do not
necessarily retain five snapshots. K8up requires a positive daily retention value;
zero defaults to 14 days. Sunday checks at 04:00 verify every stored data block;
pruning runs at 05:00.

Each K8up backup mounts the application's PVC read-only, uses SQLite's online backup
command and prepares a tar archive containing the database and a `files.tar`
archive of the remaining files before streaming it to restic. Applications
keep running. Database copies are transactional; other files are copied during
normal operation and do not form an atomic application-wide snapshot. Preparation
has a 4 GiB staging limit for both intermediate and final archives and does not
change PVC ownership.

Crafty's preparation mounts only the `app-config` subdirectory of `crafty-data-nvme`.
It copies `db/crafty.sqlite` through SQLite's backup API. Runtime `session.lock` and
recreated `db/servers` statistics/cache data are excluded; game files use Crafty's
separate SATA backups. Restore the panel configuration and game directories together.

Minecraft's native policy stops the game for the ZIP copy and restarts it only
if it was running. The panel stays up. Terraform manages this policy and its
schedule in [terraform/crafty](../terraform/crafty/README.md).

Prometheus, Alertmanager, Loki and Alloy positions have no scheduled backup.
The repository configures no offsite replication of application backups or copy
of Minecraft ZIPs off the worker. [R2 backups](../terraform/R2_BACKUP.md) cover
Terraform state only. A lost worker also makes its SATA backups unavailable.

The control plane has a separate [Talos/etcd recovery procedure](talos-etcd-recovery.md).
Its encrypted repository on Houston is independent of the application repositories.

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
Keep a separate [SealedSecrets key recovery copy](sealed-secrets-recovery.md);
application PVC backups do not contain the controller's keys.
Renew the server certificate before expiry, preserving its IP SAN and distributing
new CA trust before a CA change.

For an HTTP-password rotation, prepare the bcrypt file and matching SealedSecret.
Apply Houston's credentials while backup jobs are idle, then sync `backups` and
verify access and an existing snapshot restore. Keep repository encryption passwords
unchanged so existing snapshots remain readable.

Install CRDs before the operator. The operator chart skips Helm hooks because
its legacy cleanup hook removes old executor RBAC across namespaces. Sync backup
definitions only after storage and credentials are ready. All three ArgoCD backup
Applications (`backup-crds`, `backup-operator`, `backups`) require manual
synchronization. Before enabling schedules, run one backup and an isolated
restore per application; review retention with restic's
`forget --dry-run` before allowing pruning.

## Inspect and restore

```bash
kubectl --context homelab-prod get schedules,backups,checks,prunes -A
kubectl --context homelab-prod -n n8n logs job/JOB_NAME
ssh houston-01 'journalctl -u restic-server.service --since today'
```

For an isolated restore on the MacBook, select a snapshot belonging to a
**completed successful Backup**, not an unchecked `latest` snapshot.
Set `backup_namespace` and `database` from this table; the example uses n8n:

| Application | Namespace | Database |
| --- | --- | --- |
| Home Assistant | `home-assistant` | `home-assistant_v2.db` |
| n8n | `n8n` | `database.sqlite` |
| Grafana | `monitoring` | `grafana.db` |
| Crafty panel | `crafty-controller` | `db/crafty.sqlite` |

Run from the repository root. Open an SSH tunnel in another terminal:
`ssh -N -L 127.0.0.1:48444:10.0.70.10:8444 houston-01`.

```bash
backup_namespace=n8n
database=database.sqlite
export RESTIC_REPOSITORY="rest:https://127.0.0.1:48444/$backup_namespace/"
export RESTIC_REST_USERNAME="$backup_namespace"
export RESTIC_REST_PASSWORD="$(cat ".secrets/houston-restic/$backup_namespace.http-password")"
export RESTIC_PASSWORD_FILE="$PWD/.secrets/houston-restic/$backup_namespace.repo-password"
umask 077
restore_dir=$(mktemp -d "${TMPDIR:-/tmp}/application-restore.XXXXXX")
restic --cacert system/backups/ca.crt snapshots
restic --cacert system/backups/ca.crt ls SNAPSHOT_ID
restic --cacert system/backups/ca.crt dump SNAPSHOT_ID ARCHIVE_PATH > "$restore_dir/archive.tar"
mkdir -p "$restore_dir/data/$(dirname "$database")"
tar -xf "$restore_dir/archive.tar" -C "$restore_dir"
cp "$restore_dir/$database" "$restore_dir/data/$database"
tar -xf "$restore_dir/files.tar" -C "$restore_dir/data"
sqlite3 -readonly -bail "$restore_dir/data/$database" 'PRAGMA integrity_check;'
unset RESTIC_REST_PASSWORD
```

Replace `SNAPSHOT_ID` and `ARCHIVE_PATH` using `snapshots` and `ls` output.
For Crafty, `data/` contains `app-config/` contents, not the whole PVC.
Download the matching Minecraft ZIP from Crafty, check it with `unzip -t` and
extract it into a separate test directory. Inspect configuration and test each
application separately.
Restic integrity checks and successful job status do not replace restore tests.
An in-place restore requires explicit approval, an application stop and protection
from ArgoCD self-heal.

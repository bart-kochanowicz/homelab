# Talos and etcd recovery

`homelab-prod` has one control plane (`10.0.70.11`) and one worker
(`10.0.70.12`), running Talos 1.11.1 / Kubernetes 1.34.0 / etcd 3.6.4.
An etcd snapshot contains Kubernetes objects and Secrets, including sealing keys.
It does not contain PVC contents or the Talos configuration needed to rebuild a
machine. Preserve the snapshot and both complete machine configurations together.

Backups are manual. Take one before Talos, Kubernetes or control-plane changes.
Encrypted copies live in `/srv/terraform/backups/talos` on Houston's SSD, owned by
`capcom` with mode `700`, independently of the application REST-server repositories
and their 90 GiB limit. Access and the encryption password must work without
Kubernetes. Keep a separate offsite copy; Houston is still in the same location.

## Prepare storage once

Run from this repository in Bash with the tools from `aqua.yaml`, Talos 1.11.1,
SSH access to `houston-01`, and Docker for the offline recovery check.
The Ansible `storage` role creates the repository directory:

```bash
ANSIBLE_CONFIG=infra/ansible/ansible.cfg ansible-playbook \
  infra/ansible/playbooks/houston.yml --tags storage --ask-become-pass
set -euo pipefail
set +x
umask 077
install -d -m 700 .secrets
(set -C; openssl rand -base64 48 > .secrets/talos-etcd.repo-password)
export RESTIC_REPOSITORY=sftp:houston-01:/srv/terraform/backups/talos
export RESTIC_PASSWORD_FILE="$PWD/.secrets/talos-etcd.repo-password"
unset RESTIC_PASSWORD RESTIC_PASSWORD_COMMAND RESTIC_REPOSITORY_FILE
ssh houston-01 'mountpoint --quiet /srv/terraform'
restic init
```

Save the generated password in a password manager before relying on this copy.
For an existing repository, load its original password; do not regenerate it or
repeat `restic init`. Keep SSH recovery access outside Kubernetes as well.

## Capture and encrypt

With those Restic variables set, run in Bash during a stable configuration
window, with no concurrent upgrade or CA rotation. Explicit Talos context,
endpoint and node overrides avoid inheriting the worker as a snapshot target.

```bash
set -euo pipefail
set +x
umask 077
ssh houston-01 'mountpoint --quiet /srv/terraform'
talos_backup=$(mktemp -d "$PWD/.secrets/talos-etcd.XXXXXXXX")
talosctl --context admin@homelab-prod -e 10.0.70.11 -n 10.0.70.11 etcd status
talosctl --context admin@homelab-prod -e 10.0.70.11 -n 10.0.70.11 \
  etcd snapshot "$talos_backup/etcd.snapshot"
talosctl --context admin@homelab-prod -e 10.0.70.11 -n 10.0.70.11 \
  get mc v1alpha1 -o yaml | yq '.spec' > "$talos_backup/controlplane.yaml"
talosctl --context admin@homelab-prod -e 10.0.70.11 -n 10.0.70.12 \
  get mc v1alpha1 -o yaml | yq '.spec' > "$talos_backup/worker.yaml"
yq -e 'select(.machine.type != null) | .machine.type == "controlplane" and
  ((.machine.ca.key // "") | length > 0) and ((.cluster.ca.key // "") | length > 0)' \
  "$talos_backup/controlplane.yaml" >/dev/null
yq -e 'select(.machine.type != null) | .machine.type == "worker"' \
  "$talos_backup/worker.yaml" >/dev/null
talosctl --context admin@homelab-prod -e 10.0.70.11 -n 10.0.70.11 \
  version > "$talos_backup/versions.txt"
git rev-parse HEAD >> "$talos_backup/versions.txt"
(cd "$talos_backup" && shasum -a 256 etcd.snapshot controlplane.yaml worker.yaml versions.txt > SHA256SUMS)
tar -C "$talos_backup" -cf - etcd.snapshot controlplane.yaml worker.yaml versions.txt SHA256SUMS |
  restic backup --stdin --stdin-filename talos-etcd-recovery.tar --tag talos-etcd
restic check --read-data
restic snapshots --tag talos-etcd
```

Keep the successful snapshot ID and verify the encrypted copy below before
accepting it. `.secrets/` contains plaintext recovery credentials: retain private
permissions, never print or commit them, and keep failed staging for diagnosis.
Repeat capture after machine configuration or CA changes. Retain older verified
snapshots; inspect SSD usage before planning retention changes.

## Verify and prepare recovery offline

Use the selected `SNAPSHOT_ID`, not an unchecked `latest`. Configure the same
Restic repository/password on the recovery computer. Extraction and the helper
etcd run locally, with no network access for the helper container.

```bash
set -euo pipefail
set +x
umask 077
install -d -m 700 .secrets
verified_restore=$(mktemp -d "$PWD/.secrets/talos-restore.XXXXXXXX")
restic dump SNAPSHOT_ID /talos-etcd-recovery.tar > "$verified_restore/recovery.tar"
tar -xf "$verified_restore/recovery.tar" -C "$verified_restore"
(cd "$verified_restore" && shasum -a 256 -c SHA256SUMS)
etcd_image=gcr.io/etcd-development/etcd:v3.6.4
docker run --rm --network none --mount "type=bind,src=$verified_restore,dst=/recovery" \
  --entrypoint /usr/local/bin/etcdutl "$etcd_image" \
  snapshot restore /recovery/etcd.snapshot --data-dir /recovery/etcd-check \
  --name recovery --initial-advertise-peer-urls http://127.0.0.1:2380 \
  --initial-cluster recovery=http://127.0.0.1:2380 \
  --bump-revision 1000000000 --mark-compacted
check_container=talos-etcd-check-$(date +%s)
docker run -d --name "$check_container" --network none \
  --mount "type=bind,src=$verified_restore,dst=/recovery" \
  --entrypoint /usr/local/bin/etcd "$etcd_image" \
  --name recovery --data-dir /recovery/etcd-check \
  --listen-client-urls http://127.0.0.1:2379 --advertise-client-urls http://127.0.0.1:2379 \
  --listen-peer-urls http://127.0.0.1:2380 --initial-advertise-peer-urls http://127.0.0.1:2380 \
  --initial-cluster recovery=http://127.0.0.1:2380
docker exec "$check_container" /usr/local/bin/etcdctl --endpoints http://127.0.0.1:2379 \
  --dial-timeout=30s --command-timeout=30s snapshot save /recovery/recover.snapshot
docker rm -f "$check_container"
```

The first restore checks the snapshot's native hash. The revision bump and
compaction invalidate stale Kubernetes watches; Talos 1.11's bootstrap API does
not expose those options. Re-snapshotting produces `recover.snapshot` with a valid
integrity hash for Talos. Keep this helper isolated and never attach Kubernetes
to it. On failure, retain the files and inspect only the named helper container.
Use matching Talos/Kubernetes versions and etcd tools when recovering older copies.

## Recover the single control plane

Production reset or in-place restore requires explicit approval. First establish
that the existing control plane cannot be recovered normally. Preserve current
state where possible and review the target machine, disk and network settings.
An EPHEMERAL wipe destroys local control-plane data; preserve any local PVC data
first. The worker and its PVC disks must remain intact.

Generate fresh client credentials from the saved machine configuration. This
also works when the old client certificate expired and preserves the cluster CAs:

```bash
talosctl gen secrets --from-controlplane-config "$verified_restore/controlplane.yaml" \
  --output-file "$verified_restore/secrets.yaml"
talosctl gen config homelab-prod https://10.0.70.11:6443 \
  --with-secrets "$verified_restore/secrets.yaml" --output-types talosconfig \
  --output "$verified_restore/talosconfig"
```

Recover on replacement hardware with the original configuration and secret
material, retaining hostname `talos-p5e-e9e` and `10.0.70.11` as the API endpoint.
Review the install disk, hostname and interfaces in the saved config before applying it in maintenance mode; verify
the replacement's identity through its console. Only on replacement hardware in
maintenance mode, use its console certificate fingerprint:

```bash
talosctl -n 10.0.70.11 apply-config --insecure \
  --cert-fingerprint FINGERPRINT_FROM_CONSOLE --file "$verified_restore/controlplane.yaml"
```

For an existing failed control plane, the approved wipe is limited to that node's
EPHEMERAL partition:

```bash
talosctl --talosconfig "$verified_restore/talosconfig" -e 10.0.70.11 -n 10.0.70.11 reset \
  --graceful=false --reboot --wipe-mode=system-disk --system-labels-to-wipe=EPHEMERAL
```

The target must have machine type `controlplane` and etcd in `Preparing` state
before bootstrapping. With the recovered client configuration:

```bash
talosctl --talosconfig "$verified_restore/talosconfig" -e 10.0.70.11 -n 10.0.70.11 get machinetype
talosctl --talosconfig "$verified_restore/talosconfig" -e 10.0.70.11 -n 10.0.70.11 service etcd
talosctl --talosconfig "$verified_restore/talosconfig" -e 10.0.70.11 -n 10.0.70.11 \
  bootstrap --recover-from "$verified_restore/recover.snapshot"
talosctl --talosconfig "$verified_restore/talosconfig" -e 10.0.70.11 -n 10.0.70.11 etcd status
talosctl --talosconfig "$verified_restore/talosconfig" -e 10.0.70.11 -n 10.0.70.11 \
  health --control-plane-nodes 10.0.70.11 --worker-nodes 10.0.70.12 --wait-timeout=5m
talosctl --talosconfig "$verified_restore/talosconfig" -e 10.0.70.11 -n 10.0.70.11 \
  kubeconfig "$verified_restore/kubeconfig" --merge=false
kubectl --kubeconfig "$verified_restore/kubeconfig" get --raw=/readyz
kubectl --kubeconfig "$verified_restore/kubeconfig" get nodes -o wide
kubectl --kubeconfig "$verified_restore/kubeconfig" get applications -n argocd
```

Verify node readiness, Cilium connectivity, SealedSecret reconciliation and the
applications against their PVC data. ArgoCD does not recreate lost PVC contents;
use the [application restore procedures](backups.md) for those. Reconcile manual
bootstrap-managed components and network policies deliberately. Take a new backup
after successful recovery.

References: [Talos 1.11 recovery](https://docs.siderolabs.com/talos/v1.11/build-and-extend-talos/cluster-operations-and-maintenance/disaster-recovery),
[etcd revision bump and compaction](https://etcd.io/docs/v3.6/op-guide/recovery/#restoring-with-revision-bump).

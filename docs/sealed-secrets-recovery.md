# SealedSecrets key recovery

The controller `sealed-secrets-controller` runs in `sealed-secrets`. Its private
keys are required to decrypt the SealedSecrets in Git, including application
backup credentials. Application PVC backups do not contain these keys.

Keep an encrypted recovery copy outside the cluster and Houston. The repository
location, access credentials and encryption password must be available without
Kubernetes; do not store their only copy as a SealedSecret. Restic from `aqua.yaml`
can store this copy on an independent disk or remote repository. Initialize a new
repository once with `restic init` and keep its password in a password manager.

## Export and back up

Run from the repository root in Bash. Export **all** labelled keys, retaining old
ones: automatic renewal adds a key every 30 days by default. Repeat this backup
after renewal and before using the new certificate to seal credentials. This is
a manual procedure; no scheduled key backup is configured.

```bash
set -euo pipefail
umask 077
install -d -m 700 .secrets
key_backup=$(mktemp -d "$PWD/.secrets/sealed-secrets.XXXXXXXX")
kubectl --context homelab-prod -n sealed-secrets get secrets \
  -l sealedsecrets.bitnami.com/sealed-secrets-key -o json |
  jq '{apiVersion, kind, items: [.items[] |
    {apiVersion, kind, type, data, metadata:
      {name: .metadata.name, namespace: .metadata.namespace, labels: .metadata.labels}}]}' \
  > "$key_backup/keys.json"
jq -e '.items | length > 0' "$key_backup/keys.json" >/dev/null
kubeseal --context homelab-prod --controller-namespace sealed-secrets \
  --controller-name sealed-secrets-controller --fetch-cert > "$key_backup/controller.crt"
kubectl create secret generic sealed-secrets-recovery-check -n default \
  --from-literal=purpose=sealed-secrets-recovery-check --dry-run=client -o json |
  kubeseal --cert "$key_backup/controller.crt" --format json > "$key_backup/check.sealed.json"
```

The export keeps key data, names, namespaces and labels, omitting cluster-specific
metadata. The check secret is created locally and never submitted to Kubernetes.
Treat `keys.json` as production credentials: the private directory is mode `700`,
files are mode `600`, and `.secrets/` is ignored. Never print or commit its contents.

Set `RESTIC_REPOSITORY` to the independent recovery repository. Restic prompts for
its password; do not reuse the cluster's K8up repository or password settings.

```bash
export RESTIC_REPOSITORY=/absolute/path/to/independent-recovery-repository
unset RESTIC_PASSWORD RESTIC_PASSWORD_FILE RESTIC_PASSWORD_COMMAND
tar -C "$key_backup" -cf - keys.json check.sealed.json |
  restic backup --stdin --stdin-filename sealed-secrets-recovery.tar --tag sealed-secrets
restic check --read-data
restic snapshots --tag sealed-secrets
```

Accept the snapshot only after the offline check below; if renewal occurred
during export, repeat the export and verification. Keep the verified snapshot ID
and key names with the recovery copy. Preserve older snapshots and sealing keys;
deleting an old key can make historical Git revisions unrecoverable.
Key renewal does not rotate application passwords.

## Verify an encrypted copy offline

On a recovery machine, check out this repository and configure access to the
independent Restic repository and its password. Run from the repository root in
Bash, replacing `SNAPSHOT_ID` with the successful snapshot ID.

```bash
set -euo pipefail
umask 077
install -d -m 700 .secrets
verified_restore=$(mktemp -d "$PWD/.secrets/sealed-secrets-restore.XXXXXXXX")
restic dump SNAPSHOT_ID /sealed-secrets-recovery.tar > "$verified_restore/recovery.tar"
tar -xf "$verified_restore/recovery.tar" -C "$verified_restore"
kubeseal --recovery-unseal --recovery-private-key "$verified_restore/keys.json" \
  < "$verified_restore/check.sealed.json" > "$verified_restore/check.json"
jq -e '.metadata.name == "sealed-secrets-recovery-check" and
  .metadata.namespace == "default" and
  (.data.purpose | @base64d) == "sealed-secrets-recovery-check"' \
  "$verified_restore/check.json" >/dev/null
```

A successful check proves that the encrypted copy contains a usable key for the
test secret. It does not prove coverage of every historical SealedSecret; retain
the complete key set and compare its names with the source export.

## Restore the controller

Use a disposable cluster for rehearsals. An in-place production restore requires
explicit approval and a backup of the current keys. Never import production
sealing keys into a test cluster; rehearse with separately generated test keys.

Set `recovery_context` to the explicitly selected target. Restore into the original
`sealed-secrets` namespace before starting the controller and syncing applications:

```bash
recovery_context=RESTORE_CONTEXT
kubectl config get-contexts "$recovery_context"
kubectl --context "$recovery_context" create namespace sealed-secrets \
  --dry-run=client -o yaml | kubectl --context "$recovery_context" apply -f -
kubectl --context "$recovery_context" apply -f "$verified_restore/keys.json"
```

On a fresh cluster, start the pinned controller through the normal ArgoCD
bootstrap after importing the keys. If it is already running, retain its existing
keys and restart only the controller so it reloads the imported set:

```bash
kubectl --context "$recovery_context" -n sealed-secrets \
  rollout restart deployment/sealed-secrets-controller
kubectl --context "$recovery_context" -n sealed-secrets \
  rollout status deployment/sealed-secrets-controller --timeout=120s
kubectl --context "$recovery_context" get sealedsecrets -A
```

Verify that applications' SealedSecrets report `Synced=True` after reconciliation.
Preserve each SealedSecret's original name and namespace: strict sealing binds
both to the ciphertext. Restoring keys does not restore PVC data or Talos/etcd.

See the [upstream key backup and recovery guidance](https://github.com/bitnami/sealed-secrets#how-can-i-do-a-backup-of-my-sealedsecrets).

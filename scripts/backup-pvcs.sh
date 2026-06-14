#!/usr/bin/env bash
set -euo pipefail

: "${RESTIC_REPOSITORY:?Set RESTIC_REPOSITORY to an encrypted restic repository}"
if [[ -z "${RESTIC_PASSWORD_FILE:-}" && -z "${RESTIC_PASSWORD_COMMAND:-}" ]]; then
  echo "Set RESTIC_PASSWORD_FILE or RESTIC_PASSWORD_COMMAND" >&2
  exit 1
fi

case "$RESTIC_REPOSITORY" in
  /* | *:*) ;;
  *)
    echo "RESTIC_REPOSITORY must be an absolute path or a restic backend URI." >&2
    echo "For the external disk, use /Volumes/SanDisk/Backups/homelab-restic." >&2
    exit 1
    ;;
esac

command -v kubectl >/dev/null
command -v restic >/dev/null
command -v jq >/dev/null

readonly helper_image="busybox:1.37.0@sha256:9532d8c39891ca2ecde4d30d7710e01fb739c87a8b9299685c63704296b16028"
readonly entries=(
  "crafty-controller:crafty-controller:crafty-data"
  "home-assistant:home-assistant:home-assistant-config"
  "n8n:n8n:n8n-data"
)
readonly backup_status_namespace="monitoring"

record_backup_status() {
  local status="$1"
  local timestamp
  timestamp="$(date -u +"%Y-%m-%dT%H:%M:%S.000000Z")"
  kubectl apply -f - >/dev/null <<EOF
apiVersion: coordination.k8s.io/v1
kind: Lease
metadata:
  name: workstation-pvc-backup-${status}
  namespace: ${backup_status_namespace}
spec:
  holderIdentity: backup-pvcs.sh
  renewTime: "${timestamp}"
EOF
}

cleanup() {
  local exit_status=$?
  local entry namespace deployment
  set +e
  for entry in "${entries[@]}"; do
    IFS=: read -r namespace deployment _ <<<"$entry"
    kubectl -n "$namespace" delete pod pvc-backup --ignore-not-found --wait=false >/dev/null 2>&1 || true
    if [[ -f ".backups/${namespace}-${deployment}.replicas" ]]; then
      if kubectl -n "$namespace" scale deployment "$deployment" \
        --replicas "$(cat ".backups/${namespace}-${deployment}.replicas")" >/dev/null 2>&1; then
        rm -f ".backups/${namespace}-${deployment}.replicas"
      fi
    fi
  done
  if [[ "$exit_status" -ne 0 ]]; then
    if ! record_backup_status failure; then
      echo "Warning: unable to record the backup failure Lease." >&2
    fi
  fi
  exit "$exit_status"
}
trap cleanup EXIT

mkdir -p .backups
rm -f .backups/last-successful-restore-test
rm -rf .backups/restore-tests
restic snapshots >/dev/null 2>&1 || restic init

for entry in "${entries[@]}"; do
  IFS=: read -r namespace deployment pvc <<<"$entry"
  archive_path="/${namespace}/${pvc}.tar"
  case "$namespace" in
    crafty-controller)
      run_as_user=1000
      run_as_group=0
      run_as_non_root=true
      ;;
    n8n)
      run_as_user=1000
      run_as_group=1000
      run_as_non_root=true
      ;;
    *)
      run_as_user=0
      run_as_group=0
      run_as_non_root=false
      ;;
  esac
  kubectl -n "$namespace" delete pod pvc-backup-failed \
    --ignore-not-found --wait=false >/dev/null
  replicas="$(kubectl -n "$namespace" get deployment "$deployment" -o jsonpath='{.spec.replicas}')"
  printf '%s\n' "$replicas" > ".backups/${namespace}-${deployment}.replicas"

  kubectl -n "$namespace" scale deployment "$deployment" --replicas=0
  kubectl -n "$namespace" wait --for=delete pod \
    -l "app.kubernetes.io/name=${deployment}" --timeout=5m || true

  kubectl -n "$namespace" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: pvc-backup
spec:
  automountServiceAccountToken: false
  restartPolicy: Never
  securityContext:
    runAsNonRoot: ${run_as_non_root}
    runAsUser: ${run_as_user}
    runAsGroup: ${run_as_group}
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: archive
      image: ${helper_image}
      command: ["sh", "-c", "sleep 86400"]
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
      volumeMounts:
        - name: data
          mountPath: /data
          readOnly: true
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: ${pvc}
EOF
  kubectl -n "$namespace" wait --for=condition=Ready pod/pvc-backup --timeout=5m
  backup_succeeded=false
  for attempt in 1 2 3; do
    if kubectl --request-timeout=0 -n "$namespace" exec pvc-backup -- \
      tar -C /data -cf - . |
      restic backup --stdin --stdin-filename "$archive_path" \
        --tag homelab-pvc --tag "$namespace"; then
      backup_succeeded=true
      break
    fi
    echo "Backup stream failed for ${namespace}/${pvc}, attempt ${attempt}/3." >&2
    sleep 5
  done
  if [[ "$backup_succeeded" != "true" ]]; then
    echo "Backup failed for ${namespace}/${pvc} after 3 attempts." >&2
    exit 1
  fi
  if ! restic snapshots --tag "$namespace" --latest 1 --json |
    jq -e 'length == 1' >/dev/null; then
    echo "Restic did not finalize a snapshot for ${namespace}/${pvc}." >&2
    exit 1
  fi
  restic ls latest --tag "$namespace" "$archive_path" >/dev/null
  kubectl -n "$namespace" delete pod pvc-backup --wait=true
  kubectl -n "$namespace" scale deployment "$deployment" --replicas "$replicas"
  rm -f ".backups/${namespace}-${deployment}.replicas"
done

restic check
if ! record_backup_status success; then
  echo "Warning: unable to record the successful backup Lease." >&2
fi
date -u +"%Y-%m-%dT%H:%M:%SZ" > .backups/last-successful-backup
trap - EXIT

#!/usr/bin/env bash
set -euo pipefail

in_place=false
if [[ "${1:-}" == "--in-place" ]]; then
  in_place=true
  shift
fi

if [[ "$#" -ne 3 ]]; then
  echo "Usage: $0 [--in-place] <namespace> <deployment> <pvc>" >&2
  exit 1
fi

: "${RESTIC_REPOSITORY:?Set RESTIC_REPOSITORY}"
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

namespace="$1"
deployment="$2"
pvc="$3"
archive_path="/${namespace}/${pvc}.tar"
helper_image="busybox:1.37.0@sha256:9532d8c39891ca2ecde4d30d7710e01fb739c87a8b9299685c63704296b16028"
command -v restic >/dev/null
command -v jq >/dev/null

if ! restic snapshots --tag "$namespace" --latest 1 --json |
  jq -e 'length == 1' >/dev/null; then
  echo "No restic snapshot exists for tag ${namespace}; no workload was changed." >&2
  exit 1
fi
if ! restic ls latest --tag "$namespace" "$archive_path" >/dev/null; then
  echo "The latest ${namespace} snapshot does not contain ${archive_path}." >&2
  echo "No workload was changed." >&2
  exit 1
fi

mark_restore_test() {
  local marker_dir=".backups/restore-tests"
  mkdir -p "$marker_dir"
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "${marker_dir}/${namespace}-${pvc}"
  if [[ -f "${marker_dir}/crafty-controller-crafty-data" &&
    -f "${marker_dir}/home-assistant-home-assistant-config" &&
    -f "${marker_dir}/n8n-n8n-data" ]]; then
    date -u +"%Y-%m-%dT%H:%M:%SZ" > .backups/last-successful-restore-test
  fi
}

if [[ "$in_place" != "true" ]]; then
  : "${RESTORE_TEST_DIR:?Set RESTORE_TEST_DIR to a writable location with enough free space}"
  mkdir -p "$RESTORE_TEST_DIR"
  restore_dir="$(mktemp -d "${RESTORE_TEST_DIR%/}/${namespace}-${pvc}.XXXXXX")"
  restore_succeeded=false
  # shellcheck disable=SC2329
  cleanup_test() {
    if [[ "$restore_succeeded" != "true" ]]; then
      rm -rf "$restore_dir"
    fi
  }
  trap cleanup_test EXIT

  echo "Restoring ${namespace}/${pvc} into ${restore_dir}; Kubernetes is not modified."
  restic dump latest --tag "$namespace" "$archive_path" |
    tar -C "$restore_dir" -xf -
  if [[ -z "$(find "$restore_dir" -mindepth 1 -print -quit)" ]]; then
    echo "Restore test produced an empty directory." >&2
    exit 1
  fi
  restore_succeeded=true
  mark_restore_test
  trap - EXIT
  echo "Restore test passed. Inspect or remove: ${restore_dir}"
  exit 0
fi

if [[ "${CONFIRM_IN_PLACE_RESTORE:-}" != "yes" ]]; then
  echo "Set CONFIRM_IN_PLACE_RESTORE=yes to overwrite the live PVC." >&2
  exit 1
fi

command -v kubectl >/dev/null
replicas="$(kubectl -n "$namespace" get deployment "$deployment" -o jsonpath='{.spec.replicas}')"
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

cleanup_live() {
  kubectl -n "$namespace" delete pod pvc-restore --ignore-not-found --wait=false >/dev/null 2>&1 || true
  kubectl -n "$namespace" scale deployment "$deployment" --replicas "$replicas" >/dev/null 2>&1 || true
}
trap cleanup_live EXIT

kubectl -n "$namespace" scale deployment "$deployment" --replicas=0
kubectl -n "$namespace" wait --for=delete pod \
  -l "app.kubernetes.io/name=${deployment}" --timeout=5m || true
kubectl -n "$namespace" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: pvc-restore
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
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: ${pvc}
EOF
kubectl -n "$namespace" wait --for=condition=Ready pod/pvc-restore --timeout=5m
restic dump latest --tag "$namespace" "$archive_path" |
  kubectl --request-timeout=0 -n "$namespace" exec -i pvc-restore -- tar -C /data -xf -
kubectl -n "$namespace" delete pod pvc-restore --wait=true
kubectl -n "$namespace" scale deployment "$deployment" --replicas "$replicas"
trap - EXIT
echo "In-place restore completed for ${namespace}/${pvc}."

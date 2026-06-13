#!/usr/bin/env bash
set -euo pipefail

: "${RESTIC_REPOSITORY:?Set RESTIC_REPOSITORY to an encrypted restic repository}"
if [[ -z "${RESTIC_PASSWORD_FILE:-}" && -z "${RESTIC_PASSWORD_COMMAND:-}" ]]; then
  echo "Set RESTIC_PASSWORD_FILE or RESTIC_PASSWORD_COMMAND" >&2
  exit 1
fi

command -v kubectl >/dev/null
command -v restic >/dev/null

readonly helper_image="busybox:1.37.0@sha256:9532d8c39891ca2ecde4d30d7710e01fb739c87a8b9299685c63704296b16028"
readonly entries=(
  "crafty-controller:crafty-controller:crafty-data"
  "home-assistant:home-assistant:home-assistant-config"
  "n8n:n8n:n8n-data"
)
current_namespace=""

cleanup() {
  local exit_status=$?
  local entry namespace deployment
  set +e
  for entry in "${entries[@]}"; do
    IFS=: read -r namespace deployment _ <<<"$entry"
    kubectl -n "$namespace" delete pod pvc-backup --ignore-not-found --wait=false >/dev/null 2>&1 || true
    if [[ -f ".backups/${namespace}-${deployment}.replicas" ]]; then
      kubectl -n "$namespace" scale deployment "$deployment" \
        --replicas "$(cat ".backups/${namespace}-${deployment}.replicas")" >/dev/null 2>&1 || true
    fi
  done
  if [[ "$exit_status" -ne 0 && -n "$current_namespace" ]]; then
    kubectl -n "$current_namespace" apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: pvc-backup-failed
spec:
  automountServiceAccountToken: false
  restartPolicy: Never
  securityContext:
    runAsNonRoot: true
    runAsUser: 65534
    runAsGroup: 65534
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: marker
      image: ${helper_image}
      command: ["sh", "-c", "exit 1"]
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
EOF
  fi
  exit "$exit_status"
}
trap cleanup EXIT

mkdir -p .backups
restic snapshots >/dev/null 2>&1 || restic init

for entry in "${entries[@]}"; do
  IFS=: read -r namespace deployment pvc <<<"$entry"
  current_namespace="$namespace"
  run_as_user=0
  run_as_group=0
  run_as_non_root=false
  if [[ "$namespace" == "n8n" ]]; then
    run_as_user=1000
    run_as_group=1000
    run_as_non_root=true
  fi
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
  kubectl -n "$namespace" exec pvc-backup -- tar -C /data -cf - . |
    restic backup --stdin --stdin-filename "${namespace}/${pvc}.tar" \
      --tag homelab-pvc --tag "$namespace"
  kubectl -n "$namespace" delete pod pvc-backup --wait=true
  kubectl -n "$namespace" scale deployment "$deployment" --replicas "$replicas"
  rm -f ".backups/${namespace}-${deployment}.replicas"
done

restic check
date -u +"%Y-%m-%dT%H:%M:%SZ" > .backups/last-successful-backup
trap - EXIT

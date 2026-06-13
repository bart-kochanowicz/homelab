#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "Usage: $0 <namespace> <deployment> <pvc>" >&2
  exit 1
fi

: "${RESTIC_REPOSITORY:?Set RESTIC_REPOSITORY}"
if [[ -z "${RESTIC_PASSWORD_FILE:-}" && -z "${RESTIC_PASSWORD_COMMAND:-}" ]]; then
  echo "Set RESTIC_PASSWORD_FILE or RESTIC_PASSWORD_COMMAND" >&2
  exit 1
fi

namespace="$1"
deployment="$2"
pvc="$3"
helper_image="busybox:1.37.0@sha256:9532d8c39891ca2ecde4d30d7710e01fb739c87a8b9299685c63704296b16028"
replicas="$(kubectl -n "$namespace" get deployment "$deployment" -o jsonpath='{.spec.replicas}')"
run_as_user=0
run_as_group=0
run_as_non_root=false
if [[ "$namespace" == "n8n" ]]; then
  run_as_user=1000
  run_as_group=1000
  run_as_non_root=true
fi

cleanup() {
  kubectl -n "$namespace" delete pod pvc-restore --ignore-not-found --wait=false >/dev/null 2>&1 || true
  kubectl -n "$namespace" scale deployment "$deployment" --replicas "$replicas" >/dev/null 2>&1 || true
}
trap cleanup EXIT

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
restic dump latest --tag "$namespace" "${namespace}/${pvc}.tar" |
  kubectl -n "$namespace" exec -i pvc-restore -- tar -C /data -xf -
kubectl -n "$namespace" delete pod pvc-restore --wait=true
kubectl -n "$namespace" scale deployment "$deployment" --replicas "$replicas"
mkdir -p .backups
date -u +"%Y-%m-%dT%H:%M:%SZ" > .backups/last-successful-restore-test
trap - EXIT

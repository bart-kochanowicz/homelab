#!/usr/bin/env bash
set -euo pipefail
umask 077

mode="${1:---run}"
case "$mode" in
  --run | --recover | --maintenance) ;;
  *) echo "Usage: $0 [--run|--recover|--maintenance]" >&2; exit 1 ;;
esac
: "${BACKUP_STATE_DIR:?Set BACKUP_STATE_DIR on the Houston SSD}"
: "${KUBECONFIG:?Set KUBECONFIG to the scoped Houston backup identity}"
readonly mount_root="${BACKUP_MOUNT_ROOT:-/srv/terraform}"
readonly helper_image="busybox:1.37.0@sha256:9532d8c39891ca2ecde4d30d7710e01fb739c87a8b9299685c63704296b16028"
readonly entries=(
  "home-assistant:home-assistant:home-assistant-config:home-assistant:applications:0:0"
  "n8n:n8n:n8n-data:n8n:applications:1000:1000"
  "monitoring:kube-prometheus-stack-grafana:kube-prometheus-stack-grafana:monitoring:platform:472:472"
)
for tool in kubectl jq flock findmnt timeout sync; do command -v "$tool" >/dev/null; done
[[ "$BACKUP_STATE_DIR" == "$mount_root"/* && -d "$BACKUP_STATE_DIR" ]] || {
  echo "Backup state must be an existing directory on the Houston SSD." >&2; exit 1;
}
[[ "$(findmnt --noheadings --output TARGET --target "$BACKUP_STATE_DIR")" == "$mount_root" ]] || {
  echo "The backup SSD is not mounted; refusing to use the system disk." >&2; exit 1;
}
exec 9>"$BACKUP_STATE_DIR/operation.lock"
flock -n 9 || { echo "Another backup operation holds the lock." >&2; exit 1; }

record_status() {
  local status="$1" timestamp
  timestamp="${2:-$(date -u +'%Y-%m-%dT%H:%M:%S.000000Z')}"
  kubectl --request-timeout=15s -n monitoring patch lease "houston-pvc-backup-${status}" \
    --type=merge -p "$(jq -nc --arg time "$timestamp" '{spec:{renewTime:$time}}')" >/dev/null
}

wait_ready() {
  local namespace="$1" deployment="$2" replicas="$3" deadline=$((SECONDS + 90))
  while (( SECONDS < deadline )); do
    if kubectl --request-timeout=15s -n "$namespace" get deployment "$deployment" -o json |
      jq -e --argjson replicas "$replicas" '
        .spec.replicas == $replicas and
        (.status.observedGeneration // 0) >= .metadata.generation and
        (.status.readyReplicas // 0) == $replicas and
        (.status.availableReplicas // 0) == $replicas' >/dev/null; then
      return 0
    fi
    sleep 2
  done
  echo "${namespace}/${deployment} did not become ready; recovery state is retained." >&2
  return 1
}

recover_all() {
  local state entry namespace deployment pvc app project uid gid replicas current failed=0
  for entry in "${entries[@]}"; do
    IFS=: read -r namespace deployment pvc app project uid gid <<<"$entry"
    state="$BACKUP_STATE_DIR/${namespace}.state.json"
    [[ -f "$state" ]] || continue
    if ! jq -e --arg ns "$namespace" --arg name "$deployment" '
      .namespace == $ns and .deployment == $name and
      (.replicas | type == "number" and . >= 0 and . <= 10 and floor == .)' "$state" >/dev/null; then
      echo "Invalid recovery state: ${state}; refusing to guess." >&2
      failed=1; continue
    fi
    replicas="$(jq -r .replicas "$state")"
    if ! current="$(kubectl --request-timeout=15s -n "$namespace" get deployment "$deployment" -o jsonpath='{.spec.replicas}')"; then
      failed=1; continue
    fi
    if [[ "$current" != "$replicas" && "$current" != 0 ]]; then
      echo "Replica count changed externally for ${namespace}/${deployment}; inspect ${state}." >&2
      failed=1; continue
    fi
    if [[ "$current" != "$replicas" ]] && ! kubectl --request-timeout=15s -n "$namespace" \
      scale deployment "$deployment" --current-replicas=0 --replicas="$replicas" >/dev/null; then
      failed=1; continue
    fi
    if wait_ready "$namespace" "$deployment" "$replicas"; then
      rm "$state"
      echo "Recovered ${namespace}/${deployment} to ${replicas} replicas."
    else
      failed=1
    fi
  done
  return "$failed"
}

finish_run() {
  local result=$?
  trap - EXIT INT TERM
  if ! recover_all; then result=1; fi
  if (( result != 0 )); then
    record_status failure || echo "Unable to record the backup failure Lease." >&2
  fi
  exit "$result"
}

if [[ "$mode" == --recover ]]; then
  recover_all
  exit 0
fi

trap finish_run EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
recover_all
: "${RESTIC_REPOSITORY:?Set RESTIC_REPOSITORY on the Houston SSD}"
: "${RESTIC_PASSWORD_FILE:?Set RESTIC_PASSWORD_FILE}"
command -v restic >/dev/null
[[ "$RESTIC_REPOSITORY" == "$mount_root"/* && -f "$RESTIC_REPOSITORY/config" ]] || {
  echo "Initialize the encrypted repository explicitly before running backups." >&2; exit 1;
}
[[ "$(findmnt --noheadings --output TARGET --target "$RESTIC_REPOSITORY")" == "$mount_root" ]] || {
  echo "The repository is not on the expected mounted SSD." >&2; exit 1;
}
restic cat config >/dev/null

if [[ "$mode" == --maintenance ]]; then
  [[ -f "$BACKUP_STATE_DIR/completed-run.json" ]] || { echo "No completed backup run to verify." >&2; exit 1; }
  completed="$(jq -er '.completed | select(type == "string")' "$BACKUP_STATE_DIR/completed-run.json")"
  jq -e '.snapshots | keys == ["home-assistant", "monitoring", "n8n"]' \
    "$BACKUP_STATE_DIR/completed-run.json" >/dev/null
  for entry in "${entries[@]}"; do
    IFS=: read -r namespace deployment pvc app project uid gid <<<"$entry"
    snapshot="$(jq -er --arg ns "$namespace" '.snapshots[$ns]' "$BACKUP_STATE_DIR/completed-run.json")"
    [[ "$snapshot" =~ ^[[:xdigit:]]{64}$ ]] || { echo "Invalid completed snapshot ID." >&2; exit 1; }
    restic snapshots --json "$snapshot" | jq -e --arg path "/${namespace}/${pvc}.tar" '
      length == 1 and .[0].hostname == "houston-01" and .[0].paths == [$path] and
      (.[0].tags | index("houston-managed")) != null' >/dev/null
  done
  restic check --read-data-subset="$(date +%u)/7"
  retention=(--host houston-01 --tag houston-managed --group-by 'host,paths'
    --keep-daily "${BACKUP_KEEP_DAILY:-7}" --keep-weekly "${BACKUP_KEEP_WEEKLY:-4}"
    --keep-monthly "${BACKUP_KEEP_MONTHLY:-3}")
  if [[ "${BACKUP_PRUNE_ENABLED:-0}" == 1 ]]; then
    restic forget "${retention[@]}" --prune
  else
    restic forget "${retention[@]}" --dry-run
  fi
  record_status success "$completed"
  kubectl --request-timeout=15s -n monitoring patch lease houston-pvc-backup-failure \
    --type=merge -p '{"spec":{"renewTime":null}}' >/dev/null
  rm "$BACKUP_STATE_DIR/completed-run.json"
  trap - EXIT INT TERM
  exit 0
fi

assert_free_space() {
  local available_kib
  available_kib="$(LC_ALL=C df -Pk "$RESTIC_REPOSITORY" | awk 'NR == 2 {print $4}')"
  if [[ ! "$available_kib" =~ ^[0-9]+$ ]] || (( 10#$available_kib < 10 * 1024 * 1024 )); then
    echo "Keep at least 10 GiB free on the backup SSD; no new workload will be stopped." >&2
    return 1
  fi
}

# The deny window is declarative; this account cannot alter GitOps policies.
clock="$(TZ=Europe/Warsaw date +%H%M%S)"
(( 10#$clock >= 30015 && 10#$clock <= 30500 )) || {
  echo "Start backups only between 03:00:15 and 03:05 Europe/Warsaw." >&2; exit 1;
}
readonly copy_deadline=$(( $(date +%s) + 900 ))
rm -f "$BACKUP_STATE_DIR/completed-run.json"
snapshots='{}'

assert_window() {
  local app="$1" project="$2" now
  now="$(TZ=Europe/Warsaw date +%H%M%S)"
  (( 10#$now >= 30015 && 10#$now <= 32000 )) || { echo "Backup copy window has ended." >&2; return 1; }
  (( $(date +%s) < copy_deadline )) || { echo "Backup copy budget exhausted." >&2; return 1; }
  kubectl --request-timeout=15s -n argocd get appproject "$project" -o json |
    jq -e --arg app "$app" 'any(.spec.syncWindows[]?;
      .kind == "deny" and .schedule == "0 3 * * *" and .duration == "30m" and
      .timeZone == "Europe/Warsaw" and .manualSync == false and
      (.applications | index($app)) != null)' >/dev/null || {
        echo "The required GitOps deny window is missing for ${app}." >&2; return 1;
      }
  kubectl --request-timeout=15s -n argocd get application "$app" -o json |
    jq -e --arg project "$project" '
      .spec.project == $project and .operation == null and
      (.status.operationState.phase != "Running" and .status.operationState.phase != "Terminating") and
      .status.sync.status == "Synced"' >/dev/null || {
        echo "${app} is syncing or already out of sync; no new workload will be stopped." >&2; return 1;
      }
}

assert_helper() {
  local namespace="$1" pvc="$2" uid="$3" gid="$4"
  kubectl --request-timeout=15s -n "$namespace" get pod pvc-backup -o json |
    jq -er --arg pvc "$pvc" --arg image "$helper_image" --argjson uid "$uid" --argjson gid "$gid" '
      select(.metadata.deletionTimestamp == null and
        .spec.automountServiceAccountToken == false and
        (.spec.hostNetwork // false) == false and (.spec.hostPID // false) == false and
        (.spec.hostIPC // false) == false and .spec.securityContext.fsGroup == null and
        .spec.securityContext.runAsUser == $uid and .spec.securityContext.runAsGroup == $gid and
        (.spec.volumes | length) == 1 and .spec.volumes[0].name == "data" and
        .spec.volumes[0].persistentVolumeClaim.claimName == $pvc and
        .spec.volumes[0].persistentVolumeClaim.readOnly == true and
        (.spec.containers | length) == 1 and (.spec.initContainers // [] | length) == 0 and
        (.spec.ephemeralContainers // [] | length) == 0 and
        .spec.containers[0].name == "archive" and .spec.containers[0].image == $image and
        .spec.containers[0].command == ["sleep", "2147483647"] and
        (.spec.containers[0].env // [] | length) == 0 and
        (.spec.containers[0].envFrom // [] | length) == 0 and
        (.spec.containers[0].securityContext.privileged // false) == false and
        .spec.containers[0].securityContext.allowPrivilegeEscalation == false and
        .spec.containers[0].securityContext.readOnlyRootFilesystem == true and
        .spec.containers[0].securityContext.capabilities.drop == ["ALL"] and
        (.spec.containers[0].securityContext.capabilities.add // [] | length) == 0 and
        (.spec.containers[0].volumeMounts | length) == 1 and
        .spec.containers[0].volumeMounts[0].name == "data" and
        .spec.containers[0].volumeMounts[0].mountPath == "/data" and
        .spec.containers[0].volumeMounts[0].readOnly == true and
        any(.status.conditions[]?; .type == "Ready" and .status == "True")) | .metadata.uid'
}

assert_free_space
for entry in "${entries[@]}"; do
  IFS=: read -r namespace deployment pvc app project uid gid <<<"$entry"
  assert_window backups backups
  assert_window "$app" "$project"
  helper_uid="$(assert_helper "$namespace" "$pvc" "$uid" "$gid")"
  kubectl --request-timeout=15s -n "$namespace" get pvc "$pvc" -o json |
    jq -e '.status.phase == "Bound"' >/dev/null
done

for entry in "${entries[@]}"; do
  IFS=: read -r namespace deployment pvc app project uid gid <<<"$entry"
  assert_window backups backups
  assert_window "$app" "$project"
  helper_uid="$(assert_helper "$namespace" "$pvc" "$uid" "$gid")"
  state="$BACKUP_STATE_DIR/${namespace}.state.json"
  assert_free_space
  replicas="$(kubectl --request-timeout=15s -n "$namespace" get deployment "$deployment" -o jsonpath='{.spec.replicas}')"
  jq -ne --arg ns "$namespace" --arg name "$deployment" --argjson replicas "$replicas" \
    'select($replicas >= 0 and $replicas <= 10 and ($replicas | floor) == $replicas) |
      {namespace:$ns,deployment:$name,replicas:$replicas}' > "$state.tmp"
  mv "$state.tmp" "$state"
  sync -f "$state"
  kubectl --request-timeout=15s -n "$namespace" scale deployment "$deployment" \
    --current-replicas="$replicas" --replicas=0 >/dev/null

  stop_deadline=$((SECONDS + 120))
  while ! kubectl --request-timeout=15s -n "$namespace" get pods -o json |
    jq -e --arg pvc "$pvc" --arg helper "$helper_uid" '[.items[] |
      select(.metadata.uid != $helper and .status.phase != "Succeeded" and .status.phase != "Failed") |
      select(any(.spec.volumes[]?; .persistentVolumeClaim.claimName == $pvc))] | length == 0' >/dev/null; do
    (( SECONDS < stop_deadline )) || { echo "PVC ${namespace}/${pvc} still has users; backup aborted." >&2; exit 1; }
    sleep 2
  done
  assert_window backups backups
  helper_uid="$(assert_helper "$namespace" "$pvc" "$uid" "$gid")"
  remaining=$((copy_deadline - $(date +%s)))
  (( remaining > 0 )) || { echo "No copy budget remains." >&2; exit 1; }
  archive_path="/${namespace}/${pvc}.tar"
  excludes=()
  case "$namespace" in
    home-assistant) excludes=('--exclude=./home-assistant.log*') ;;
    n8n) excludes=('--exclude=./n8nEventLog*.log') ;;
  esac
  result_file="$BACKUP_STATE_DIR/${namespace}.result.json"
  timeout --signal=TERM --kill-after=10s "${remaining}s" restic backup --json \
    --host houston-01 --tag homelab-pvc --tag houston-managed --tag "$namespace" \
    --stdin-filename "$archive_path" --stdin-from-command -- \
    kubectl --request-timeout=0 -n "$namespace" exec pvc-backup -c archive -- \
      tar -C /data -cf - "${excludes[@]}" . > "$result_file"
  snapshot="$(jq -er 'select(.message_type == "summary") | .snapshot_id' "$result_file")"
  [[ "$snapshot" =~ ^[[:xdigit:]]{64}$ ]] || { echo "Missing exact snapshot ID." >&2; exit 1; }
  restic snapshots --json "$snapshot" | jq -e --arg path "$archive_path" '
    length == 1 and .[0].hostname == "houston-01" and .[0].paths == [$path] and
    (.[0].tags | index("houston-managed")) != null' >/dev/null
  restic ls --json "$snapshot" "$archive_path" | jq -se --arg path "$archive_path" '
    [.[] | select(.struct_type == "node" and .type == "file" and .path == $path and .size > 1024)] |
    length == 1' >/dev/null
  recover_all
  snapshots="$(jq -nc --argjson previous "$snapshots" --arg ns "$namespace" --arg id "$snapshot" \
    '$previous + {($ns):$id}')"
  echo "Backed up ${namespace}/${pvc}: ${snapshot}."
done

jq -n --arg time "$(date -u +'%Y-%m-%dT%H:%M:%S.000000Z')" --argjson snapshots "$snapshots" \
  '{completed:$time,snapshots:$snapshots}' > "$BACKUP_STATE_DIR/completed-run.json.tmp"
mv "$BACKUP_STATE_DIR/completed-run.json.tmp" "$BACKUP_STATE_DIR/completed-run.json"
sync -f "$BACKUP_STATE_DIR/completed-run.json"
trap - EXIT INT TERM
echo "All three PVC backups are complete and workloads are restored."

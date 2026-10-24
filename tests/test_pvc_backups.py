import copy
from contextlib import closing
import json
import os
from pathlib import Path
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/backup-pvcs.sh"
FIXTURES = ROOT / "tests/fixtures/backups"


class PvcBackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.restic = shutil.which("restic")
        if not cls.restic:
            raise RuntimeError("Install the pinned restic from aqua.yaml before running backup tests")
        cls.resources = []
        for directory in ("system/backups", "system/argocd"):
            rendered = subprocess.run(["kubectl", "kustomize", str(ROOT / directory)],
                                      capture_output=True, text=True, check=True)
            decoded = subprocess.run(["yq", "-o=json", "-I=0", "select(.kind != null)"],
                                     input=rendered.stdout, capture_output=True, text=True, check=True)
            cls.resources.extend(json.loads(line) for line in decoded.stdout.splitlines() if line.strip())

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="houston-backup-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.state = self.root / "state"
        self.state.mkdir()
        self.repo = self.root / "restic"
        self.data = self.root / "data"
        self.password = self.root / "password"
        self.password.write_text("isolated-test-repository\n")
        self.cluster_path = self.root / "cluster.json"
        cluster = {"faults": {}, "calls": [], "leases": {}, "deployments": {},
                   "helpers": {}, "applications": {}, "projects": {}}
        for resource in copy.deepcopy(self.resources):
            kind, name = resource["kind"], resource["metadata"]["name"]
            if kind == "AppProject":
                cluster["projects"][name] = resource
            if kind == "Application" and name in {
                    "backups", "monitoring", "home-assistant", "n8n"}:
                cluster["applications"][name] = {"spec": resource["spec"],
                                               "status": {"sync": {"status": "Synced"}}}
            if kind != "Pod" or name != "pvc-backup":
                continue
            namespace = resource["metadata"]["namespace"]
            resource["metadata"]["uid"] = "helper-" + namespace
            resource["status"] = {"conditions": [{"type": "Ready", "status": "True"}]}
            cluster["helpers"][namespace] = resource
            pvc = resource["spec"]["volumes"][0]["persistentVolumeClaim"]["claimName"]
            deployment = "kube-prometheus-stack-grafana" if namespace == "monitoring" else namespace
            cluster["deployments"][namespace] = {"name": deployment, "pvc": pvc, "replicas": 1}
            cluster["applications"].setdefault(namespace, {
                "spec": {"project": "platform" if namespace == "monitoring" else "applications"},
                "status": {"sync": {"status": "Synced"}}})
            directory = self.data / namespace
            directory.mkdir(parents=True)
            with closing(sqlite3.connect(directory / "application.db")) as database, database:
                database.execute("CREATE TABLE settings (name TEXT PRIMARY KEY, value TEXT)")
                database.execute("INSERT INTO settings VALUES ('namespace', ?)", (namespace,))
            (directory / "config.json").write_text(json.dumps({"namespace": namespace}))
        self.cluster_path.write_text(json.dumps(cluster))
        self.env = os.environ | {
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            "BACKUP_MOUNT_ROOT": str(self.root), "BACKUP_STATE_DIR": str(self.state),
            "KUBECONFIG": str(self.root / "unused-kubeconfig"),
            "RESTIC_REPOSITORY": str(self.repo), "RESTIC_PASSWORD_FILE": str(self.password),
            "RESTIC_CACHE_DIR": str(self.root / "cache"), "GOMAXPROCS": "2",
            "TEST_CLUSTER_STATE": str(self.cluster_path), "TEST_DATA_ROOT": str(self.data),
            "TEST_MOUNT_OK": "1", "TEST_MOUNT_ROOT": str(self.root),
            "TEST_DF_COUNTER": str(self.root / "df-counter"),
        }
        self.install_stub("kubectl", f"exec {shlex.quote(sys.executable)} {shlex.quote(str(FIXTURES / 'kubectl.py'))} \"$@\"")
        self.install_stub("findmnt", '[ "$TEST_MOUNT_OK" = 1 ] && printf "%s\\n" "$TEST_MOUNT_ROOT" || printf "/\\n"')
        self.install_stub("df", '''available=${TEST_DF_AVAILABLE_KIB:-67108864}
if [ -n "${TEST_DF_LOW_AFTER:-}" ]; then
  count=$(cat "$TEST_DF_COUNTER" 2>/dev/null || echo 0)
  count=$((count + 1))
  printf '%s\\n' "$count" > "$TEST_DF_COUNTER"
  if [ "$count" -gt "$TEST_DF_LOW_AFTER" ]; then available=1048576; fi
fi
printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n/dev/test 251658240 1 %s 1%% %s\\n' "$available" "$TEST_MOUNT_ROOT"''')
        self.install_stub("flock", "exit 0")
        self.install_stub("date", 'case "$*" in *+%H%M%S*) echo 030030;; *+%s*) echo 1792810830;; *+%u*) echo 6;; *) /bin/date "$@";; esac')
        self.install_stub("timeout", 'shift 3; exec "$@"')
        sync_code = "import os,sys; fd=os.open(sys.argv[1], os.O_RDONLY); os.fsync(fd); os.close(fd)"
        self.install_stub("sync", f'[ "$1" = -f ] && exec {shlex.quote(sys.executable)} '
                          f'-c {shlex.quote(sync_code)} "$2"')
        self.restic_command("init")

    def install_stub(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def cluster(self):
        return json.loads(self.cluster_path.read_text())

    def edit_cluster(self, update):
        cluster = self.cluster()
        update(cluster)
        self.cluster_path.write_text(json.dumps(cluster))

    def restic_command(self, *args):
        return subprocess.run([self.restic, *args], env=self.env, capture_output=True,
                              check=True, timeout=30)

    def snapshots(self):
        return json.loads(self.restic_command("snapshots", "--json").stdout)

    def run_backup(self, mode="--run", success=True):
        result = subprocess.run(["bash", str(SCRIPT), mode], env=self.env,
                                capture_output=True, text=True, timeout=45)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def assert_no_scale(self):
        self.assertFalse([call for call in self.cluster()["calls"] if call[1] == "scale"])

    def assert_restored(self):
        self.assertEqual({item["replicas"] for item in self.cluster()["deployments"].values()}, {1})
        self.assertFalse(list(self.state.glob("*.state.json")))

    def test_backup_identity_can_only_scale_named_apps_and_exec_readonly_helpers(self):
        for role in (item for item in self.resources if item["kind"] == "Role"):
            namespace = role["metadata"]["namespace"]
            rules = role["rules"]
            for rule in rules:
                self.assertNotIn("*", rule["apiGroups"])
                self.assertNotIn("*", rule["resources"])
                self.assertNotIn("*", rule["verbs"])
                self.assertNotIn("secrets", rule["resources"])
                if "pods" in rule["resources"]:
                    self.assertEqual(set(rule["verbs"]), {"get", "list"})
                if "pods/exec" in rule["resources"]:
                    self.assertEqual(rule["resourceNames"], ["pvc-backup"])
                    self.assertEqual(set(rule["verbs"]), {"get", "create"})
                if "deployments/scale" in rule["resources"]:
                    self.assertEqual(rule["resourceNames"], [self.cluster()["deployments"][namespace]["name"]])
                if any(resource in rule["resources"] for resource in ("applications", "appprojects")):
                    self.assertEqual(rule["verbs"], ["get"])
                    self.assertTrue(rule["resourceNames"])
        bindings = [item for item in self.resources if item["kind"] == "RoleBinding"]
        self.assertEqual({item["metadata"]["namespace"] for item in bindings},
                         {"home-assistant", "n8n", "monitoring", "argocd"})
        for binding in bindings:
            self.assertEqual(binding["subjects"], [{"apiGroup": "rbac.authorization.k8s.io",
                                                   "kind": "User", "name": "houston-backup"}])
        for helper in self.cluster()["helpers"].values():
            self.assertFalse(helper["spec"]["automountServiceAccountToken"])
            self.assertTrue(helper["spec"]["volumes"][0]["persistentVolumeClaim"]["readOnly"])
            self.assertTrue(helper["spec"]["containers"][0]["volumeMounts"][0]["readOnly"])
        policies = [item for item in self.resources if item["kind"] == "NetworkPolicy"
                    and item["metadata"]["name"] == "pvc-backup-isolation"]
        self.assertEqual(len(policies), 3)
        for policy in policies:
            self.assertEqual(set(policy["spec"]["policyTypes"]), {"Ingress", "Egress"})
            self.assertEqual(policy["spec"]["ingress"], [])
            self.assertEqual(policy["spec"]["egress"], [])

    def test_exact_nightly_deny_windows_protect_apps_and_helpers(self):
        expected = {"applications": ["home-assistant", "n8n"],
                    "platform": ["monitoring"], "backups": ["backups"]}
        for project, applications in expected.items():
            self.assertEqual(self.cluster()["projects"][project]["spec"]["syncWindows"], [{
                "kind": "deny", "schedule": "0 3 * * *", "duration": "30m",
                "timeZone": "Europe/Warsaw", "applications": applications, "manualSync": False,
            }])

    def test_three_snapshots_restore_real_sqlite_data_and_only_maintenance_records_success(self):
        self.run_backup()
        snapshots = self.snapshots()
        self.assertEqual(len(snapshots), 3)
        self.assert_restored()
        self.assertNotIn("houston-pvc-backup-success", self.cluster()["leases"])
        self.assertTrue((self.state / "completed-run.json").exists())
        for snapshot in snapshots:
            namespace = snapshot["paths"][0].split("/")[1]
            archive = self.root / f"{namespace}.tar"
            with archive.open("wb") as stream:
                subprocess.run([self.restic, "dump", snapshot["id"], snapshot["paths"][0]],
                               env=self.env, stdout=stream, stderr=subprocess.PIPE, check=True, timeout=15)
            restored = self.root / "restored" / namespace
            restored.mkdir(parents=True)
            with tarfile.open(archive) as bundle:
                bundle.extractall(restored, filter="data")
            with closing(sqlite3.connect(restored / "application.db")) as database:
                self.assertEqual(database.execute("PRAGMA integrity_check").fetchone(), ("ok",))
                self.assertEqual(database.execute("SELECT value FROM settings").fetchone(), (namespace,))
        completed_path = self.state / "completed-run.json"
        completed = json.loads(completed_path.read_text())
        completed["completed"] = "2026-10-23T01:05:00.000000Z"
        completed_path.write_text(json.dumps(completed))
        self.run_backup("--maintenance")
        self.assertEqual(self.cluster()["leases"]["houston-pvc-backup-success"]["renewTime"],
                         completed["completed"], "Maintenance must not refresh the backup timestamp")
        self.assertFalse((self.state / "completed-run.json").exists())

    def test_producer_failure_never_finalizes_a_snapshot_or_leaves_the_app_stopped(self):
        self.edit_cluster(lambda cluster: cluster["faults"].update(producer_failure="home-assistant"))
        self.run_backup(success=False)
        self.assertEqual(self.snapshots(), [])
        self.assert_restored()
        self.assertIn("houston-pvc-backup-failure", self.cluster()["leases"])
        self.assertFalse((self.state / "completed-run.json").exists())

    def test_wrong_password_does_not_reinitialize_repository_or_stop_apps(self):
        original_config = (self.repo / "config").read_bytes()
        self.password.write_text("incorrect-test-password\n")
        self.run_backup(success=False)
        self.assert_no_scale()
        self.assertEqual((self.repo / "config").read_bytes(), original_config)

    def test_failed_preflight_never_stops_any_app(self):
        for key, value, reason in (
                ("missing_window", "platform", "required GitOps deny window"),
                ("active_application", "n8n", "syncing or already out of sync"),
                ("forbidden_helper", "monitoring", "Forbidden: helper read denied")):
            with self.subTest(fault=key):
                self.edit_cluster(lambda cluster: cluster.update(faults={key: value}, calls=[]))
                result = self.run_backup(success=False)
                self.assertIn(reason, result.stderr)
                self.assert_no_scale()

    def test_missing_mount_never_stops_apps(self):
        self.env["TEST_MOUNT_OK"] = "0"
        self.run_backup(success=False)
        self.assert_no_scale()

    def test_low_disk_space_never_stops_apps(self):
        self.env["TEST_DF_AVAILABLE_KIB"] = "1048576"
        result = self.run_backup(success=False)
        self.assertIn("at least 10 GiB free", result.stderr)
        self.assert_no_scale()
        self.assertEqual(self.snapshots(), [])

    def test_disk_reserve_is_rechecked_before_stopping_the_next_app(self):
        self.env["TEST_DF_LOW_AFTER"] = "2"
        result = self.run_backup(success=False)
        self.assertIn("at least 10 GiB free", result.stderr)
        stops = [call for call in self.cluster()["calls"]
                 if call[1] == "scale" and "--replicas=0" in call]
        self.assertEqual([call[0] for call in stops], ["home-assistant"])
        self.assertEqual(len(self.snapshots()), 1)
        self.assert_restored()

    def test_low_disk_space_does_not_prevent_workload_recovery(self):
        self.env["TEST_DF_AVAILABLE_KIB"] = "1048576"
        (self.state / "n8n.state.json").write_text(json.dumps({
            "namespace": "n8n", "deployment": "n8n", "replicas": 1}))
        self.edit_cluster(lambda cluster: cluster["deployments"]["n8n"].update(replicas=0))
        self.run_backup("--recover")
        self.assert_restored()

    def test_writable_helper_is_rejected_before_stopping_apps(self):
        self.edit_cluster(lambda cluster: cluster["helpers"]["n8n"]["spec"]["containers"][0]
                          ["volumeMounts"][0].update(readOnly=False))
        self.run_backup(success=False)
        self.assert_no_scale()

    def test_unexpected_pvc_writer_blocks_archive_and_interruption_recovers_app(self):
        self.edit_cluster(lambda cluster: cluster["faults"].update(extra_writer="home-assistant"))
        self.install_stub("sleep", 'kill -TERM "$PPID"; exit 0')
        self.run_backup(success=False)
        self.assertFalse([call for call in self.cluster()["calls"]
                          if call[1] == "exec" and "tar" in call])
        self.assertEqual(self.snapshots(), [])
        self.assert_restored()

    def test_restart_failure_retains_durable_state_and_recover_succeeds_later(self):
        self.edit_cluster(lambda cluster: cluster["faults"].update(restart_failure="home-assistant"))
        self.run_backup(success=False)
        self.assertTrue((self.state / "home-assistant.state.json").exists())
        self.assertEqual(self.cluster()["deployments"]["home-assistant"]["replicas"], 0)
        self.edit_cluster(lambda cluster: cluster["faults"].clear())
        self.run_backup("--recover")
        self.assert_restored()

    def test_recovery_does_not_overwrite_an_external_replica_change(self):
        (self.state / "n8n.state.json").write_text(json.dumps({
            "namespace": "n8n", "deployment": "n8n", "replicas": 1}))
        self.edit_cluster(lambda cluster: cluster["deployments"]["n8n"].update(replicas=2))
        self.run_backup("--recover", success=False)
        self.assert_no_scale()
        self.assertTrue((self.state / "n8n.state.json").exists())
        self.assertEqual(self.cluster()["deployments"]["n8n"]["replicas"], 2)

    def test_partial_run_cannot_trigger_maintenance_success(self):
        self.edit_cluster(lambda cluster: cluster["faults"].update(producer_failure="n8n"))
        self.run_backup(success=False)
        self.assertEqual(len(self.snapshots()), 1)
        self.run_backup("--maintenance", success=False)
        self.assertNotIn("houston-pvc-backup-success", self.cluster()["leases"])
        self.assert_restored()

    def test_incomplete_completion_manifest_cannot_trigger_maintenance_success(self):
        (self.state / "completed-run.json").write_text(json.dumps({
            "completed": "2026-10-24T01:05:00Z", "snapshots": {"home-assistant": "0" * 64}}))
        self.run_backup("--maintenance", success=False)
        self.assertNotIn("houston-pvc-backup-success", self.cluster()["leases"])

    def test_retention_does_not_prune_unrelated_snapshots(self):
        unrelated = self.root / "unrelated.txt"
        unrelated.write_text("Separate backup policy\n")
        for timestamp in ("2020-01-01 01:00:00", "2020-01-02 01:00:00"):
            self.restic_command("backup", "--host", "houston-01", "--tag", "unrelated",
                                "--time", timestamp, str(unrelated))
        protected = {item["id"] for item in self.snapshots()}
        managed = self.root / "managed.txt"
        managed.write_text("Managed retention fixture\n")
        for timestamp in ("2020-01-01 01:00:00", "2020-01-02 01:00:00"):
            self.restic_command("backup", "--host", "houston-01", "--tag", "houston-managed",
                                "--time", timestamp, str(managed))
        managed_before = {item["id"] for item in self.snapshots()} - protected
        self.run_backup()
        self.env.update(BACKUP_PRUNE_ENABLED="1", BACKUP_KEEP_DAILY="1",
                        BACKUP_KEEP_WEEKLY="1", BACKUP_KEEP_MONTHLY="1")
        self.run_backup("--maintenance")
        remaining = {item["id"] for item in self.snapshots()}
        self.assertTrue(protected <= remaining)
        self.assertEqual(len(managed_before & remaining), 1)


if __name__ == "__main__":
    unittest.main()

from contextlib import closing
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
DATABASES = {"home-assistant": "home-assistant_v2.db",
             "n8n": "database.sqlite", "monitoring": "grafana.db",
             "crafty-controller": "db/crafty.sqlite"}


class PvcBackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for tool in ("sqlite3", "restic", "tar", "yq", "helm"):
            if not shutil.which(tool):
                raise RuntimeError(f"Install {tool} before running backup tests")
        rendered = subprocess.run(["helm", "template", "backups", str(ROOT / "system/backups")],
                                  capture_output=True, text=True, check=True)
        parsed = subprocess.run(["yq", "-o=json", "-I=0", "select(.kind != null)"],
                                input=rendered.stdout, capture_output=True, text=True, check=True)
        cls.resources = [json.loads(line) for line in parsed.stdout.splitlines() if line.strip()]
        cls.prebackups = {item["metadata"]["namespace"]: item for item in cls.resources
                          if item["kind"] == "PreBackupPod"}

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="homelab-backup-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def prepare(self, namespace, source, staging):
        init = self.prebackups[namespace]["spec"]["pod"]["spec"]["initContainers"][0]
        paths = {"data": str(source), "staging": str(staging)}
        command = re.sub(r"(?<![\w/])/(data|staging)(?=/|\s|$)",
                         lambda match: paths[match[1]], init["args"][0])
        return subprocess.run(["sh", "-ec", command], env=os.environ | {"COPYFILE_DISABLE": "1"},
                              capture_output=True, text=True, timeout=30)

    def archive_path(self, namespace, staging):
        command = shlex.split(self.prebackups[namespace]["spec"]["backupCommand"])
        self.assertEqual(command[0], "cat")
        self.assertEqual(len(command), 2)
        return Path(command[1].replace("/staging", str(staging)))

    def source(self, namespace):
        source, staging = self.root / namespace / "source", self.root / namespace / "staging"
        source.mkdir(parents=True)
        staging.mkdir()
        (source / DATABASES[namespace]).parent.mkdir(parents=True, exist_ok=True)
        (source / ".storage").mkdir()
        (source / ".storage/settings.json").write_text('{"fixture": "nested configuration"}\n')
        (source / "config.yaml").write_text("fixture: application configuration\n")
        return source, staging

    def open_wal(self, namespace, source):
        database = sqlite3.connect(source / DATABASES[namespace])
        self.addCleanup(database.close)
        database.execute("PRAGMA journal_mode=WAL")
        database.execute("PRAGMA wal_autocheckpoint=0")
        database.execute("CREATE TABLE settings (value TEXT)")
        database.execute("INSERT INTO settings VALUES ('committed WAL data')")
        database.commit()
        self.assertGreater((source / (DATABASES[namespace] + "-wal")).stat().st_size, 0)
        return database

    def assert_database(self, namespace, directory):
        with closing(sqlite3.connect(directory / DATABASES[namespace])) as database:
            self.assertEqual(database.execute("PRAGMA integrity_check").fetchone(), ("ok",))
            self.assertEqual(database.execute("SELECT value FROM settings").fetchall(),
                             [("committed WAL data",)])

    def test_readonly_wal_backups_restore_databases_and_nested_configuration_through_restic(self):
        password = self.root / "password"
        password.write_text("isolated-test-repository\n")
        password.chmod(0o600)
        environment = os.environ | {"RESTIC_REPOSITORY": str(self.root / "repository"),
                                    "RESTIC_PASSWORD_FILE": str(password),
                                    "RESTIC_CACHE_DIR": str(self.root / "cache"), "GOMAXPROCS": "2"}
        subprocess.run(["restic", "init"], env=environment, capture_output=True, check=True, timeout=30)
        for namespace in DATABASES:
            with self.subTest(namespace=namespace):
                source, staging = self.source(namespace)
                self.open_wal(namespace, source)
                originals = {path: path.read_bytes() for path in source.rglob("*")
                             if path.is_file() and not path.name.endswith("-shm")}
                for path in source.rglob("*"):
                    path.chmod(0o555 if path.is_dir() else 0o444)
                source.chmod(0o555)
                try:
                    prepared = self.prepare(namespace, source, staging)
                finally:
                    source.chmod(0o700)
                    for path in source.rglob("*"):
                        path.chmod(0o700 if path.is_dir() else 0o600)
                self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
                for path, contents in originals.items():
                    self.assertEqual(path.read_bytes(), contents, "Source data must remain unchanged")
                archive = self.archive_path(namespace, staging)
                with archive.open("rb") as stream:
                    result = subprocess.run(
                        ["restic", "backup", "--json", "--stdin", "--stdin-filename", f"/{namespace}.tar"],
                        env=environment, stdin=stream, capture_output=True, text=True, check=True, timeout=30,
                    )
                snapshot = next(json.loads(line)["snapshot_id"] for line in result.stdout.splitlines()
                                if json.loads(line).get("message_type") == "summary")
                restored_tar = self.root / f"{namespace}.tar"
                with restored_tar.open("wb") as stream:
                    subprocess.run(["restic", "dump", snapshot, f"/{namespace}.tar"],
                                   env=environment, stdout=stream, stderr=subprocess.PIPE, check=True, timeout=30)
                restored = self.root / namespace / "restored"
                restored.mkdir()
                with tarfile.open(restored_tar) as bundle:
                    bundle.extractall(restored, filter="data")
                with tarfile.open(restored / "files.tar") as files:
                    files.extractall(restored, filter="data")
                self.assert_database(namespace, restored)
                self.assertEqual((restored / "config.yaml").read_text(),
                                 "fixture: application configuration\n")
                self.assertEqual((restored / ".storage/settings.json").read_text(),
                                 '{"fixture": "nested configuration"}\n')

    def test_sata_provisioning_rejects_other_claims_before_creating_directories(self):
        script = subprocess.run(
            ["yq", ".data.setup", str(ROOT / "system/local-path-provisioner/configmap.yaml")],
            capture_output=True, text=True, check=True).stdout
        calls = self.root / "calls"
        commands = self.root / "bin"
        commands.mkdir()
        for command in ("mkdir", "chown"):
            executable = commands / command
            executable.write_text('#!/bin/sh\nprintf "%s\\n" "$0 $*" >> "$CALLS"\n')
            executable.chmod(0o700)
        cases = {
            "/var/mnt/minecraft/crafty-controller/crafty-data/pvc-test": True,
            "/var/mnt/minecraft/pvc-test_crafty-controller_crafty-data": True,
            "/var/mnt/minecraft/monitoring/grafana-data/pvc-test": False,
            "/var/mnt/minecraft/pvc-test_n8n_n8n-data": False,
            "/var/mnt/minecraft/crafty-controller/servers/pvc-test": False,
            "/var/mnt/minecraft": False,
            "/var/mnt/nvme/n8n/n8n-data-nvme/pvc-test": True,
        }
        for path, allowed in cases.items():
            with self.subTest(path=path):
                calls.unlink(missing_ok=True)
                result = subprocess.run(
                    ["sh", "-ec", script], capture_output=True, text=True,
                    env=os.environ | {"VOL_DIR": path, "CALLS": str(calls),
                                      "PATH": str(commands) + os.pathsep + os.environ["PATH"]})
                self.assertEqual(result.returncode == 0, allowed, result.stderr)
                self.assertEqual(calls.exists(), allowed)
                if not allowed:
                    self.assertIn("reserved for Crafty backups", result.stderr)

    def test_crafty_sata_claim_is_mounted_only_as_backups(self):
        rendered = subprocess.run(["kubectl", "kustomize", str(ROOT / "apps/crafty-controller")],
                                  capture_output=True, text=True, check=True).stdout
        parsed = subprocess.run(["yq", "-o=json", "-I=0", "select(.kind != null)"],
                                input=rendered, capture_output=True, text=True, check=True)
        resources = [json.loads(line) for line in parsed.stdout.splitlines() if line.strip()]
        claims = [item for item in resources if item["kind"] == "PersistentVolumeClaim"
                  and item["spec"]["storageClassName"] == "local-path"]
        self.assertEqual([item["metadata"]["name"] for item in claims], ["crafty-data"])
        pod = next(item for item in resources if item["kind"] == "Deployment")["spec"]["template"]["spec"]
        volume = next(item["name"] for item in pod["volumes"]
                      if item.get("persistentVolumeClaim", {}).get("claimName") == "crafty-data")
        mounts = [mount for container in pod.get("initContainers", []) + pod["containers"]
                  for mount in container.get("volumeMounts", []) if mount["name"] == volume]
        self.assertEqual([(mount["mountPath"], mount["subPath"]) for mount in mounts],
                         [("/crafty/backups", "backups")])

    def test_missing_database_fails_before_producing_an_archive(self):
        source, staging = self.source("n8n")
        result = self.prepare("n8n", source, staging)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.archive_path("n8n", staging).exists())

    def test_corrupt_database_fails_before_producing_an_archive(self):
        source, staging = self.source("monitoring")
        (source / DATABASES["monitoring"]).write_bytes(b"not a SQLite database\n")
        result = self.prepare("monitoring", source, staging)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.archive_path("monitoring", staging).exists())

    def test_archive_contains_prepared_database_without_live_wal_or_application_logs(self):
        source, staging = self.source("home-assistant")
        self.open_wal("home-assistant", source)
        (source / "home-assistant.log").write_text("excluded log fixture\n")
        (source / "home-assistant.log.1").write_text("excluded rotated log fixture\n")
        result = self.prepare("home-assistant", source, staging)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with tarfile.open(self.archive_path("home-assistant", staging)) as bundle:
            names = {name.removeprefix("./") for name in bundle.getnames()}
        self.assertEqual(names, {DATABASES["home-assistant"], "files.tar"})
        with tarfile.open(staging / "files.tar") as files:
            names = {name.removeprefix("./") for name in files.getnames()}
        self.assertIn(".storage/settings.json", names)
        self.assertFalse({DATABASES["home-assistant"] + suffix for suffix in ("", "-wal", "-shm")} & names)
        self.assertFalse({"home-assistant.log", "home-assistant.log.1"} & names)

    def test_crafty_copy_excludes_disposable_stats_and_the_runtime_lock(self):
        source, staging = self.source("crafty-controller")
        self.open_wal("crafty-controller", source)
        (source / "db/servers/example").mkdir(parents=True)
        (source / "db/servers/example/crafty_server_stats.sqlite").write_bytes(b"live stats fixture")
        (source / "session.lock").write_text("runtime lock fixture")
        prepared = self.prepare("crafty-controller", source, staging)
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        with tarfile.open(staging / "files.tar") as files:
            names = {name.removeprefix("./") for name in files.getnames()}
        self.assertNotIn("session.lock", names)
        self.assertFalse(any(name.startswith("db/servers") for name in names))
        self.assertFalse({"db/crafty.sqlite" + suffix for suffix in ("", "-wal", "-shm")} & names)

    def test_crafty_preparation_mounts_only_panel_configuration_and_keeps_four_weekly_copies(self):
        spec = self.prebackups["crafty-controller"]["spec"]["pod"]["spec"]
        source = next(volume for volume in spec["volumes"] if "persistentVolumeClaim" in volume)
        self.assertEqual(source["persistentVolumeClaim"]["claimName"], "crafty-data-nvme")
        mount = next(mount for mount in spec["initContainers"][0]["volumeMounts"]
                     if mount["name"] == source["name"])
        self.assertEqual(mount["subPath"], "app-config")
        schedule = next(item["spec"] for item in self.resources if item["kind"] == "Schedule"
                        and item["metadata"]["namespace"] == "crafty-controller")
        self.assertEqual(schedule["backup"]["schedule"], "0 3 * * 1")
        self.assertEqual(schedule["prune"]["retention"], {
            "keepDaily": 1, "keepWeekly": 4,
            "hostnames": ["crafty-controller"], "tags": ["homelab"],
        })

    def test_preparation_is_tokenless_and_only_init_containers_can_access_live_pvcs(self):
        self.assertEqual(set(self.prebackups), set(DATABASES))
        for namespace, resource in self.prebackups.items():
            with self.subTest(namespace=namespace):
                spec = resource["spec"]["pod"]["spec"]
                self.assertFalse(spec["automountServiceAccountToken"])
                self.assertNotIn("fsGroup", spec["securityContext"])
                self.assertFalse(spec.get("hostNetwork", False))
                self.assertFalse(spec.get("hostPID", False))
                self.assertEqual(len(spec["initContainers"]), 1)
                self.assertEqual(len(spec["containers"]), 1)
                live = next(volume for volume in spec["volumes"] if "persistentVolumeClaim" in volume)
                self.assertTrue(live["persistentVolumeClaim"]["readOnly"])
                init_mount = next(mount for mount in spec["initContainers"][0]["volumeMounts"]
                                  if mount["name"] == live["name"])
                self.assertTrue(init_mount["readOnly"])
                main_mounts = spec["containers"][0]["volumeMounts"]
                self.assertNotIn(live["name"], {mount["name"] for mount in main_mounts})
                self.assertTrue(all(mount["readOnly"] for mount in main_mounts))
                self.assertNotIn("KUBECONFIG", json.dumps(spec))

    def test_schedules_select_only_prepared_backups_and_require_private_authenticated_tls(self):
        schedules = {item["metadata"]["namespace"]: item for item in self.resources
                     if item["kind"] == "Schedule"}
        self.assertEqual(set(schedules), set(DATABASES))
        for namespace, schedule in schedules.items():
            with self.subTest(namespace=namespace):
                spec = schedule["spec"]
                selectors = spec["backup"]["labelSelectors"]
                labels = self.prebackups[namespace]["metadata"]["labels"]
                self.assertTrue(selectors)
                self.assertTrue(any(selector.get("matchLabels") and
                                    all(labels.get(key) == value for key, value in selector["matchLabels"].items())
                                    for selector in selectors))
                self.assertTrue(spec["backend"]["rest"]["url"].startswith("https://10.0.70.10:8444/"))
                self.assertTrue(spec["backend"]["rest"]["userSecretRef"])
                self.assertTrue(spec["backend"]["rest"]["passwordSecretReg"])
                self.assertTrue(spec["backend"]["repoPasswordSecretRef"])
                self.assertTrue(spec["backend"]["tlsOptions"]["caCert"].startswith("/"))
                self.assertNotIn("KUBECONFIG", json.dumps(spec))
        self.assertFalse(any(item["kind"] in {"Role", "RoleBinding", "Lease", "PersistentVolumeClaim"}
                             for item in self.resources))


if __name__ == "__main__":
    unittest.main()

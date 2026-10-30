import json
import tarfile

from .support import DATABASES, PvcBackupTestCase


class PvcPreparationTests(PvcBackupTestCase):
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

    def test_archive_contains_prepared_database_without_live_wal_or_application_logs(
        self,
    ):
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
        self.assertFalse(
            {DATABASES["home-assistant"] + suffix for suffix in ("", "-wal", "-shm")}
            & names
        )
        self.assertFalse({"home-assistant.log", "home-assistant.log.1"} & names)

    def test_crafty_copy_excludes_disposable_stats_and_the_runtime_lock(self):
        source, staging = self.source("crafty-controller")
        self.open_wal("crafty-controller", source)
        (source / "db/servers/example").mkdir(parents=True)
        (source / "db/servers/example/crafty_server_stats.sqlite").write_bytes(
            b"live stats fixture"
        )
        (source / "session.lock").write_text("runtime lock fixture")
        prepared = self.prepare("crafty-controller", source, staging)
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        with tarfile.open(staging / "files.tar") as files:
            names = {name.removeprefix("./") for name in files.getnames()}
        self.assertNotIn("session.lock", names)
        self.assertFalse(any(name.startswith("db/servers") for name in names))
        self.assertFalse(
            {"db/crafty.sqlite" + suffix for suffix in ("", "-wal", "-shm")} & names
        )

    def test_crafty_preparation_mounts_only_panel_configuration_and_keeps_four_weekly_copies(
        self,
    ):
        spec = self.prebackups["crafty-controller"]["spec"]["pod"]["spec"]
        source = next(
            volume for volume in spec["volumes"] if "persistentVolumeClaim" in volume
        )
        self.assertEqual(
            source["persistentVolumeClaim"]["claimName"], "crafty-data-nvme"
        )
        mount = next(
            mount
            for mount in spec["initContainers"][0]["volumeMounts"]
            if mount["name"] == source["name"]
        )
        self.assertEqual(mount["subPath"], "app-config")
        schedule = next(
            item["spec"]
            for item in self.resources
            if item["kind"] == "Schedule"
            and item["metadata"]["namespace"] == "crafty-controller"
        )
        self.assertEqual(schedule["backup"]["schedule"], "0 3 * * 1")
        self.assertEqual(
            schedule["prune"]["retention"],
            {
                "keepDaily": 1,
                "keepWeekly": 4,
                "hostnames": ["crafty-controller"],
                "tags": ["homelab"],
            },
        )

    def test_preparation_is_tokenless_and_only_init_containers_can_access_live_pvcs(
        self,
    ):
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
                live = next(
                    volume
                    for volume in spec["volumes"]
                    if "persistentVolumeClaim" in volume
                )
                self.assertTrue(live["persistentVolumeClaim"]["readOnly"])
                init_mount = next(
                    mount
                    for mount in spec["initContainers"][0]["volumeMounts"]
                    if mount["name"] == live["name"]
                )
                self.assertTrue(init_mount["readOnly"])
                main_mounts = spec["containers"][0]["volumeMounts"]
                self.assertNotIn(live["name"], {mount["name"] for mount in main_mounts})
                self.assertTrue(all(mount["readOnly"] for mount in main_mounts))
                self.assertNotIn("KUBECONFIG", json.dumps(spec))

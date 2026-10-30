import json
import os
import subprocess

from .support import ROOT, PvcBackupTestCase


class PvcStorageTests(PvcBackupTestCase):
    def test_sata_provisioning_rejects_other_claims_before_creating_directories(self):
        script = subprocess.run(
            [
                "yq",
                ".data.setup",
                str(ROOT / "system/local-path-provisioner/configmap.yaml"),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
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
                    ["sh", "-ec", script],
                    capture_output=True,
                    text=True,
                    env=os.environ
                    | {
                        "VOL_DIR": path,
                        "CALLS": str(calls),
                        "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                    },
                )
                self.assertEqual(result.returncode == 0, allowed, result.stderr)
                self.assertEqual(calls.exists(), allowed)
                if not allowed:
                    self.assertIn("reserved for Crafty backups", result.stderr)

    def test_crafty_sata_claim_is_mounted_only_as_backups(self):
        rendered = subprocess.run(
            ["kubectl", "kustomize", str(ROOT / "apps/crafty-controller")],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        parsed = subprocess.run(
            ["yq", "-o=json", "-I=0", "select(.kind != null)"],
            input=rendered,
            capture_output=True,
            text=True,
            check=True,
        )
        resources = [
            json.loads(line) for line in parsed.stdout.splitlines() if line.strip()
        ]
        claims = [
            item
            for item in resources
            if item["kind"] == "PersistentVolumeClaim"
            and item["spec"]["storageClassName"] == "local-path"
        ]
        self.assertEqual([item["metadata"]["name"] for item in claims], ["crafty-data"])
        pod = next(item for item in resources if item["kind"] == "Deployment")["spec"][
            "template"
        ]["spec"]
        volume = next(
            item["name"]
            for item in pod["volumes"]
            if item.get("persistentVolumeClaim", {}).get("claimName") == "crafty-data"
        )
        mounts = [
            mount
            for container in pod.get("initContainers", []) + pod["containers"]
            for mount in container.get("volumeMounts", [])
            if mount["name"] == volume
        ]
        self.assertEqual(
            [(mount["mountPath"], mount["subPath"]) for mount in mounts],
            [("/crafty/backups", "backups")],
        )

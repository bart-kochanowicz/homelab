import subprocess
import time
from urllib.error import HTTPError
from urllib.request import urlopen

import yaml

from .support import ROOT, LoggingTestCase


class CollectorTests(LoggingTestCase):
    def test_collector_sources_are_readonly_and_do_not_change_pvc_ownership(self):
        pod = next(
            item["spec"]["template"]["spec"]
            for item in self.resources
            if item["kind"] == "StatefulSet" and item["metadata"]["name"] == "alloy"
        )
        self.assertNotIn("fsGroup", pod["securityContext"])
        self.assertTrue(pod["securityContext"]["runAsNonRoot"])
        live = [
            volume for volume in pod["volumes"] if "persistentVolumeClaim" in volume
        ]
        self.assertEqual(len(live), 1)
        self.assertTrue(live[0]["persistentVolumeClaim"]["readOnly"])
        for mount in pod["containers"][0]["volumeMounts"]:
            if mount["name"] == live[0]["name"]:
                self.assertTrue(mount["readOnly"])
        for resource in self.resources:
            if resource["kind"] == "ClusterRole":
                self.assertTrue(
                    all(
                        set(rule["resources"]) <= {"pods", "pods/log"}
                        for rule in resource["rules"]
                    )
                )

    def test_loki_starts_with_root_owned_local_path_permissions(self):
        pod = next(
            item["spec"]["template"]["spec"]
            for item in self.resources
            if item["kind"] == "StatefulSet" and item["metadata"]["name"] == "loki"
        )
        security = pod["securityContext"]
        self.assertTrue(security["runAsNonRoot"])
        self.assertNotEqual(security["runAsUser"], 0)
        provisioner = yaml.safe_load(
            (ROOT / "system/local-path-provisioner/configmap.yaml").read_text()
        )
        helper = yaml.safe_load(provisioner["data"]["helperPod.yaml"])["spec"][
            "containers"
        ][0]["image"]
        name = self.name + "-permissions"
        volume = name + "-data"
        self.command("docker", "volume", "create", volume)
        self.addCleanup(
            subprocess.run,
            ["docker", "volume", "rm", volume],
            capture_output=True,
            check=False,
        )
        self.addCleanup(
            subprocess.run,
            ["docker", "rm", "-f", name],
            capture_output=True,
            check=False,
        )
        self.command(
            "docker",
            "run",
            "--rm",
            "--user",
            "0:0",
            "--cap-drop",
            "ALL",
            "-v",
            f"{volume}:/data",
            helper,
            "chmod",
            "0770",
            "/data",
        )
        self.command(
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--user",
            f"{security['runAsUser']}:{security['runAsGroup']}",
            "--cap-drop",
            "ALL",
            "--read-only",
            "--tmpfs",
            "/tmp",
            "-p",
            "127.0.0.1::3100",
            "-v",
            f"{self.path}/loki.yaml:/etc/loki/config.yaml:ro",
            "-v",
            f"{self.path}/runtime.yaml:/etc/loki/runtime-config/runtime-config.yaml:ro",
            "-v",
            f"{volume}:/var/loki",
            "-v",
            f"{self.path}/rules:/etc/loki/rules:ro",
            self.images["loki"],
            "-config.file=/etc/loki/config.yaml",
        )
        port = self.command("docker", "port", name, "3100/tcp").rsplit(":", 1)[1]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with urlopen(f"http://127.0.0.1:{port}/ready", timeout=2) as response:
                    if response.status == 200:
                        return
            except OSError as error:
                if isinstance(error, HTTPError):
                    error.close()
                if (
                    self.command(
                        "docker", "inspect", "--format", "{{.State.Running}}", name
                    )
                    != "true"
                ):
                    self.fail(self.command("docker", "logs", name))
                time.sleep(1)
        self.fail("Loki did not become ready with local-path permissions")

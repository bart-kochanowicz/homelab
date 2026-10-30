"""Exercise log parsing and backup alerts with the pinned Loki/Alloy binaries."""

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
LOGGING = ROOT / "system/logging"


class LoggingTests(unittest.TestCase):
    @classmethod
    def command(cls, *args):
        return subprocess.check_output(
            args, text=True, stderr=subprocess.STDOUT
        ).strip()

    @classmethod
    def setUpClass(cls):
        if not shutil.which("docker"):
            raise unittest.SkipTest(
                "Docker is required for native log integration tests"
            )
        try:
            cls.command("docker", "info", "--format", "{{.ServerVersion}}")
        except subprocess.CalledProcessError as error:
            raise unittest.SkipTest("Docker daemon is unavailable") from error
        cls.directory = tempfile.TemporaryDirectory(prefix="homelab-logging-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.path = Path(cls.directory.name)
        cls.path.chmod(0o755)
        cls.containers = []
        cls.test_user = f"{os.getuid()}:{os.getgid()}"
        cls.addClassCleanup(cls.cleanup_containers)
        rendered = cls.command(
            "helm", "template", "logging", str(LOGGING), "--namespace", "monitoring"
        )
        cls.resources = list(yaml.safe_load_all(rendered))
        cls.images = {
            item["metadata"]["name"]: item["spec"]["template"]["spec"]["containers"][0][
                "image"
            ]
            for item in cls.resources
            if item["kind"] == "StatefulSet"
        }
        cls.expression = yaml.safe_load((LOGGING / "minecraft-rules.yaml").read_text())[
            "groups"
        ][0]["rules"][0]["expr"]
        config = next(
            item["data"]["config.yaml"]
            for item in cls.resources
            if item["kind"] == "ConfigMap" and item["metadata"]["name"] == "loki"
        )
        config = yaml.safe_load(config)
        config["memberlist"]["join_members"] = []
        config["common"]["ring"] = {"kvstore": {"store": "inmemory"}}
        config["common"]["compactor_grpc_address"] = "127.0.0.1:9095"
        config.setdefault("ingester", {}).setdefault("lifecycler", {})[
            "min_ready_duration"
        ] = "0s"
        config["ruler"]["alertmanager_url"] = "http://127.0.0.1:9093"
        (cls.path / "loki.yaml").write_text(yaml.safe_dump(config))
        runtime = next(
            item["data"]["runtime-config.yaml"]
            for item in cls.resources
            if item["kind"] == "ConfigMap"
            and item["metadata"]["name"] == "loki-runtime"
        )
        (cls.path / "runtime.yaml").write_text(runtime)
        for name in ("data", "positions", "logs", "rules"):
            (cls.path / name).mkdir(mode=0o777)
            (cls.path / name).chmod(0o777)
        cls.name = "homelab-log-test-" + uuid.uuid4().hex[:10]
        cls.containers.append(cls.name)
        cls.command(
            "docker",
            "run",
            "-d",
            "--name",
            cls.name,
            "--user",
            cls.test_user,
            "--cap-drop",
            "ALL",
            "--read-only",
            "--tmpfs",
            "/tmp",
            "-p",
            "127.0.0.1::3100",
            "-p",
            "127.0.0.1::1515",
            "-p",
            "127.0.0.1::1516",
            "-p",
            "127.0.0.1::12345",
            "-v",
            f"{cls.path}/loki.yaml:/etc/loki/config.yaml:ro",
            "-v",
            f"{cls.path}/runtime.yaml:/etc/loki/runtime-config/runtime-config.yaml:ro",
            "-v",
            f"{cls.path}/data:/var/loki",
            "-v",
            f"{cls.path}/rules:/etc/loki/rules:ro",
            cls.images["loki"],
            "-config.file=/etc/loki/config.yaml",
        )
        cls.wait_ready()

    @classmethod
    def cleanup_containers(cls):
        for name in reversed(cls.containers):
            subprocess.run(
                ["docker", "rm", "-f", name], check=False, capture_output=True
            )

    @classmethod
    def wait_ready(cls):
        port = cls.command("docker", "port", cls.name, "3100/tcp").rsplit(":", 1)[1]
        cls.url = "http://127.0.0.1:" + port
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                with urlopen(cls.url + "/ready", timeout=2) as response:
                    if response.status == 200:
                        return
            except OSError as error:
                if isinstance(error, HTTPError):
                    error.close()
                if (
                    cls.command(
                        "docker", "inspect", "--format", "{{.State.Running}}", cls.name
                    )
                    != "true"
                ):
                    raise AssertionError(
                        "Loki exited: " + cls.command("docker", "logs", cls.name)
                    )
                time.sleep(1)
        raise AssertionError(
            "Loki did not become ready: " + cls.command("docker", "logs", cls.name)
        )

    @classmethod
    def query(cls, expression, at=None):
        params = {"query": expression}
        if at is not None:
            params["time"] = str(at)
        url = cls.url + "/loki/api/v1/query?" + urlencode(params)
        try:
            with urlopen(url, timeout=20) as response:
                payload = json.load(response)
        except HTTPError as error:
            raise AssertionError(error.read().decode()) from error
        if payload["status"] != "success":
            raise AssertionError(payload)
        return payload["data"]["result"]

    def push(self, server, events, message="backup integration fixture"):
        streams = []
        for status, age in events:
            stamp = time.time_ns() - int(age.total_seconds() * 1_000_000_000)
            streams.append(
                {
                    "stream": {
                        "service_name": "crafty-controller",
                        "source": "file",
                        "server_name": server,
                        "backup_status": status,
                    },
                    "values": [[str(stamp), message]],
                }
            )
        request = Request(
            self.url + "/loki/api/v1/push",
            data=json.dumps({"streams": streams}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=10) as response:
            self.assertEqual(response.status, 204)

    def unhealthy(self, server, at=None):
        expression = self.expression.replace("ATM10 8.3", server)
        return any(
            result["metric"].get("server_name") == server
            for result in self.query(expression, at)
        )

    def test_weekly_copy_does_not_alert_between_runs(self):
        server = "weekly-healthy"
        self.push(server, [("success", timedelta(days=7))])
        self.assertFalse(self.unhealthy(server))

    def test_failed_copy_alerts_without_any_prior_success(self):
        server = "first-attempt-failed"
        self.push(server, [("failure", timedelta(minutes=1))])
        self.assertTrue(self.unhealthy(server))

    def test_startup_failure_is_a_recent_event_alert(self):
        rules = yaml.safe_load((LOGGING / "minecraft-rules.yaml").read_text())[
            "groups"
        ][0]["rules"]
        expression = next(
            rule["expr"] for rule in rules if rule["alert"] == "CraftyBackupStartFailed"
        )
        self.push(
            "startup-failure",
            [("event", timedelta(minutes=1))],
            "app.classes.shared.server - Failed to start backup: fixture",
        )
        self.assertTrue(self.query(expression))
        self.assertFalse(
            self.query(expression, time.time_ns() + 16 * 60 * 1_000_000_000)
        )

    def test_new_success_clears_failure_and_later_failure_reopens_it(self):
        server = "backup-retry"
        self.push(server, [("failure", timedelta(minutes=3))])
        self.assertTrue(self.unhealthy(server))
        self.push(server, [("success", timedelta(minutes=2))])
        self.assertFalse(self.unhealthy(server))
        self.push(server, [("failure", timedelta(minutes=1))])
        self.assertTrue(self.unhealthy(server))

    def test_missing_copy_cannot_be_hidden_by_another_server(self):
        self.push("another-server", [("success", timedelta(minutes=1))])
        self.assertTrue(self.unhealthy("never-copied"))
        self.push("stale-copy", [("success", timedelta(days=9))])
        self.assertTrue(self.unhealthy("stale-copy"))

    def test_absent_history_stays_unhealthy_after_failure_retention_expires(self):
        server = "expired-failure-history"
        self.push(server, [("failure", timedelta(minutes=1))])
        self.assertTrue(self.unhealthy(server))
        self.assertTrue(
            self.unhealthy(server, time.time_ns() + 15 * 86400 * 1_000_000_000)
        )

    def test_loki_restart_preserves_success_history(self):
        server = "persisted-success"
        self.push(server, [("success", timedelta(minutes=1))])
        self.assertFalse(self.unhealthy(server))
        self.command("docker", "restart", self.name)
        self.wait_ready()
        self.assertFalse(self.unhealthy(server))

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

    def test_talos_service_and_kernel_destinations_match_private_listeners(self):
        service = next(
            item["spec"]
            for item in self.resources
            if item["kind"] == "Service" and item["metadata"]["name"] == "talos-logs"
        )
        self.assertEqual(service["externalTrafficPolicy"], "Local")
        for role in ("control-plane", "worker"):
            port = next(
                port["nodePort"] for port in service["ports"] if port["name"] == role
            )
            documents = list(
                yaml.safe_load_all(
                    (ROOT / f"talos/patches/logging-{role}.yaml").read_text()
                )
            )
            endpoint = f"tcp://10.0.70.12:{port}"
            self.assertEqual(
                documents[0]["machine"]["logging"]["destinations"][0]["endpoint"],
                endpoint,
            )
            self.assertEqual(documents[1]["kind"], "KmsgLogConfig")
            self.assertEqual(documents[1]["url"], endpoint)

    def test_real_crafty_lines_keep_event_times_and_multiline_failures(self):
        server = "pipeline-fixture"
        config = (LOGGING / "config.alloy").read_text()
        # Exercise the production file pipeline without Kubernetes discovery or game logs.
        config = (
            'loki.source.file "crafty" {'
            + config.split('loki.source.file "crafty" {', 1)[1]
        )
        config = (
            config.split('loki.source.file "minecraft" {', 1)[0]
            + 'loki.write "local" {'
            + config.split('loki.write "local" {', 1)[1]
        )
        config = config.replace(
            "http://loki.monitoring.svc:3100", "http://127.0.0.1:3100"
        )
        (self.path / "alloy.alloy").write_text(config)
        from zoneinfo import ZoneInfo

        stamp = datetime.now(timezone.utc) - timedelta(days=1)

        def line(instant, message):
            local = instant.astimezone(ZoneInfo("Europe/Warsaw")).strftime(
                "%Y-%m-%d %H:%M:%S,%f"
            )[:-3]
            return f"{local} - [Crafty] - INFO - app.classes.shared.backup_mgr - {message}\n"

        (self.path / "logs/commander.log").write_text(
            line(
                stamp - timedelta(days=20),
                "Failed to create backup of server old (ID fixture)",
            )
            + line(stamp, f"Backup of server: {server} completed")
            + line(
                stamp + timedelta(milliseconds=100),
                f"Failed to create backup of server {server} (ID fixture)",
            )
            + "Traceback (most recent call last):\n  OSError: fixture\n"
        )
        name = self.name + "-alloy"
        self.containers.append(name)
        self.command(
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--user",
            self.test_user,
            "--network",
            "container:" + self.name,
            "--cap-drop",
            "ALL",
            "-v",
            f"{self.path}/alloy.alloy:/etc/alloy/config.alloy:ro",
            "-v",
            f"{self.path}/logs:/var/log/crafty:ro",
            "-v",
            f"{self.path}/positions:/var/lib/alloy",
            self.images["alloy"],
            "run",
            "--storage.path=/var/lib/alloy",
            "/etc/alloy/config.alloy",
        )
        deadline = time.monotonic() + 30
        query = f'count_over_time({{source="file",server_name="{server}",backup_status="failure"}}[2d])'
        while time.monotonic() < deadline:
            if self.query(query):
                break
            time.sleep(1)
        else:
            self.fail(
                "Alloy did not deliver the failure: "
                + self.command("docker", "logs", name)
            )
        self.assertTrue(self.unhealthy(server))
        self.assertFalse(
            self.query('count_over_time({source="file",server_name="old"}[14d])')
        )
        self.assertFalse(
            self.query(f'count_over_time({{source="file",server_name="{server}"}}[1h])')
        )
        self.command("docker", "stop", name)
        self.assertTrue(self.unhealthy(server))

    def test_talos_tcp_fragments_keep_kernel_service_node_and_time(self):
        config = (LOGGING / "config.alloy").read_text()
        config = (
            'loki.source.syslog "talos" {'
            + config.split('loki.source.syslog "talos" {', 1)[1]
        )
        config = config.replace(
            "http://loki.monitoring.svc:3100", "http://127.0.0.1:3100"
        )
        (self.path / "talos.alloy").write_text(config)
        name = self.name + "-talos"
        self.containers.append(name)
        self.command(
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--user",
            self.test_user,
            "--network",
            "container:" + self.name,
            "--cap-drop",
            "ALL",
            "-v",
            f"{self.path}/talos.alloy:/etc/alloy/config.alloy:ro",
            self.images["alloy"],
            "run",
            "--stability.level=experimental",
            "--storage.path=/tmp/alloy",
            "--server.http.listen-addr=0.0.0.0:12345",
            "/etc/alloy/config.alloy",
        )
        self.addCleanup(
            subprocess.run, ["docker", "stop", name], capture_output=True, check=False
        )
        metrics_port = self.command("docker", "port", self.name, "12345/tcp").rsplit(
            ":", 1
        )[1]
        deadline = time.monotonic() + 15
        while True:
            try:
                with urlopen(
                    f"http://127.0.0.1:{metrics_port}/-/ready", timeout=2
                ) as response:
                    if response.status == 200:
                        break
            except OSError as error:
                if isinstance(error, HTTPError):
                    error.close()
            if time.monotonic() > deadline:
                self.fail("Alloy not ready: " + self.command("docker", "logs", name))
            time.sleep(0.2)
        stamp = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        service = {
            "talos-time": stamp,
            "talos-level": "info",
            "talos-service": "kubelet",
            "msg": "TCP fixture ☃",
        }
        kernel = {
            "talos-time": stamp,
            "talos-level": "warn",
            "msg": "kernel fixture",
            "seq": 11,
        }
        worker = {
            "talos-time": stamp,
            "talos-level": "info",
            "talos-service": "containerd",
            "msg": "worker fixture",
        }
        for port, records in ((1515, [service, kernel]), (1516, [worker])):
            host_port = int(
                self.command("docker", "port", self.name, f"{port}/tcp").rsplit(":", 1)[
                    1
                ]
            )
            deadline = time.monotonic() + 15
            while True:
                try:
                    connection = socket.create_connection(
                        ("127.0.0.1", host_port), timeout=2
                    )
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        self.fail(
                            "Talos listener unavailable: "
                            + self.command("docker", "logs", name)
                        )
                    time.sleep(0.2)
            with connection:
                data = b"".join(
                    json.dumps(record, ensure_ascii=False).encode() + b"\n"
                    for record in records
                )
                marker = data.find("☃".encode())
                split = marker + 1 if marker >= 0 else 11
                connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                connection.sendall(data[:split])
                time.sleep(0.02)
                connection.sendall(data[split:])
        expression = 'sum(count_over_time({source="talos"}[10m]))'
        result = []
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            result = self.query(expression)
            if result and float(result[0]["value"][1]) == 3:
                break
            time.sleep(0.2)
        else:
            with urlopen(
                f"http://127.0.0.1:{metrics_port}/metrics", timeout=2
            ) as response:
                metrics = "\n".join(
                    line
                    for line in response.read().decode().splitlines()
                    if "syslog" in line or "dropped" in line
                )
            self.fail(
                f"Talos records missing ({result}): {metrics}\n"
                + self.command("docker", "logs", name)
            )
        self.assertTrue(
            self.query(
                'count_over_time({source="talos",node="talos-p5e-e9e",service_name="kernel"}[10m])'
            )
        )
        self.assertTrue(
            self.query(
                'count_over_time({source="talos",node="talos-2jn-7he",service_name="containerd"}[10m])'
            )
        )
        self.assertTrue(
            self.query(
                'count_over_time({source="talos",node="talos-p5e-e9e"} |= "☃" [10m])'
            )
        )
        self.assertFalse(self.query('count_over_time({source="talos"}[1m])'))


if __name__ == "__main__":
    unittest.main()

import json
import socket
import subprocess
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import urlopen

import yaml

from .support import LOGGING, ROOT, LoggingTestCase


class TalosLogTests(LoggingTestCase):
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

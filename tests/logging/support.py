"""Exercise log parsing and backup alerts with the pinned Loki/Alloy binaries."""

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parents[2]
LOGGING = ROOT / "system/logging"


class LoggingTestCase(unittest.TestCase):
    containers: list[str]

    @classmethod
    def command(cls, *args: str) -> str:
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
    def query(cls, expression: str, at: float | None = None) -> list[dict[str, Any]]:
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

    def push(
        self,
        server: str,
        events: list[tuple[str, timedelta]],
        message: str = "backup integration fixture",
    ) -> None:
        streams: list[dict[str, Any]] = []
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

    def unhealthy(self, server: str, at: float | None = None) -> bool:
        expression = self.expression.replace("ATM10 8.3", server)
        return any(
            result["metric"].get("server_name") == server
            for result in self.query(expression, at)
        )

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / ".cache/metallb-schemas"
ENVOY_SCHEMAS = ROOT / ".cache/envoy-gateway-schemas"


class GatewayTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SCHEMAS.is_dir() or not ENVOY_SCHEMAS.is_dir():
            raise RuntimeError(
                "Run make validate-metallb validate-envoy-gateway before these tests"
            )
        result = subprocess.run(
            [
                "yq",
                "-o=json",
                "-I=0",
                "select(. != null)",
                str(ROOT / ".cache/rendered/system-gateways.yaml"),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        cls.resources = [
            json.loads(line) for line in result.stdout.splitlines() if line.strip()
        ]
        cls.resources += cls.rendered("system-metallb-config.yaml")

    def resources_of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [item for item in self.resources if item["kind"] == kind]

    def validate(self, document: dict[str, Any]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory(
            prefix="gateway-schema-", dir=ROOT / ".cache"
        ) as directory:
            fixture = Path(directory) / "resource.json"
            fixture.write_text(json.dumps(document))
            return subprocess.run(
                [
                    "kubeconform",
                    "-strict",
                    "-summary",
                    "-schema-location",
                    str(
                        (
                            ENVOY_SCHEMAS
                            if document["apiVersion"].startswith(
                                "gateway.envoyproxy.io/"
                            )
                            else SCHEMAS
                        )
                        / "{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"
                    ),
                    str(fixture),
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

    @staticmethod
    def rendered(name: str) -> list[dict[str, Any]]:
        result = subprocess.run(
            [
                "yq",
                "-o=json",
                "-I=0",
                "select(. != null)",
                str(ROOT / ".cache/rendered" / name),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def acl_rules(acl: str) -> dict[str, list[tuple[str, str]]]:
    """Parse a Mosquitto ACL file into (access, topic filter) rules per user."""
    rules: dict[str, list[tuple[str, str]]] = {}
    user = None
    for line in acl.splitlines():
        words = line.split()
        if not words or words[0].startswith("#"):
            continue
        if words[0] == "user":
            user = words[1]
            rules[user] = []
        elif words[0] == "topic" and user is not None:
            # Without an access word, Mosquitto grants readwrite.
            access, topic = words[1:] if len(words) == 3 else ("readwrite", words[1])
            rules[user].append((access, topic))
    return rules


def topic_matches(pattern: str, topic: str) -> bool:
    """MQTT topic filter matching of an ACL pattern against a concrete topic."""
    wanted = topic.split("/")
    for index, level in enumerate(pattern.split("/")):
        if level == "#":
            return True
        if index >= len(wanted) or level not in ("+", wanted[index]):
            return False
    return len(pattern.split("/")) == len(wanted)


def acl_allows(
    rules: dict[str, list[tuple[str, str]]], user: str, access: str, topic: str
) -> bool:
    return any(
        topic_matches(pattern, topic) and granted in (access, "readwrite")
        for granted, pattern in rules[user]
    )

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / ".cache/gateway-api-schemas"
SCHEMA_LOCATION = str(SCHEMAS / "{{.ResourceKind}}_{{.ResourceAPIVersion}}.json")


def resource(kind: str, spec: dict[str, Any], version: str = "v1") -> dict[str, Any]:
    return {
        "apiVersion": f"gateway.networking.k8s.io/{version}",
        "kind": kind,
        "metadata": {"name": "example"},
        "spec": spec,
    }


HTTP_ROUTE = resource(
    "HTTPRoute",
    {
        "parentRefs": [{"name": "example", "sectionName": "https"}],
        "hostnames": ["app.example.invalid"],
        "rules": [{"backendRefs": [{"name": "backend", "port": 8080}]}],
    },
)


class GatewaySchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SCHEMAS.is_dir():
            raise RuntimeError("Run make validate-gateway-api before these tests")

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
                    SCHEMA_LOCATION,
                    str(fixture),
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

    def test_required_gateway_resources(self):
        examples = [
            resource(
                "GatewayClass", {"controllerName": "io.cilium/gateway-controller"}
            ),
            resource(
                "Gateway",
                {
                    "gatewayClassName": "example",
                    "listeners": [
                        {
                            "name": "https",
                            "protocol": "HTTPS",
                            "port": 443,
                            "hostname": "app.example.invalid",
                            "tls": {
                                "mode": "Terminate",
                                "certificateRefs": [{"name": "frontend-tls"}],
                            },
                            "allowedRoutes": {
                                "namespaces": {
                                    "from": "Selector",
                                    "selector": {
                                        "matchLabels": {
                                            "example.invalid/access": "private"
                                        }
                                    },
                                }
                            },
                        }
                    ],
                },
            ),
            HTTP_ROUTE,
            resource(
                "GRPCRoute",
                {
                    "parentRefs": [{"name": "example"}],
                    "rules": [{"backendRefs": [{"name": "backend", "port": 8080}]}],
                },
            ),
            resource(
                "BackendTLSPolicy",
                {
                    "targetRefs": [{"group": "", "kind": "Service", "name": "backend"}],
                    "validation": {
                        "hostname": "backend.example.svc.cluster.local",
                        "caCertificateRefs": [
                            {"group": "", "kind": "ConfigMap", "name": "backend-ca"}
                        ],
                    },
                },
            ),
            resource(
                "ReferenceGrant",
                {
                    "from": [
                        {
                            "group": "gateway.networking.k8s.io",
                            "kind": "HTTPRoute",
                            "namespace": "example",
                        }
                    ],
                    "to": [{"group": "", "kind": "Service", "name": "backend"}],
                },
                version="v1beta1",
            ),
            resource(
                "TLSRoute",
                {
                    "parentRefs": [{"name": "example"}],
                    "hostnames": ["app.example.invalid"],
                    "rules": [{"backendRefs": [{"name": "backend", "port": 8443}]}],
                },
            ),
        ]
        for example in examples:
            with self.subTest(kind=example["kind"]):
                result = self.validate(example)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(
                    "Valid: 1, Invalid: 0, Errors: 0, Skipped: 0", result.stdout
                )

    def test_unknown_fields_inside_backend_arrays_are_rejected(self):
        route = copy.deepcopy(HTTP_ROUTE)
        route["spec"]["rules"][0]["backendRefs"][0]["insecureSkipVerify"] = True
        result = self.validate(route)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid: 1", result.stdout)

    def test_invalid_backend_port_type_is_rejected(self):
        route = copy.deepcopy(HTTP_ROUTE)
        route["spec"]["rules"][0]["backendRefs"][0]["port"] = "8080"
        result = self.validate(route)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid: 1", result.stdout)

    def test_invalid_hostname_is_rejected(self):
        route = copy.deepcopy(HTTP_ROUTE)
        route["spec"]["hostnames"] = ["https://app.example.invalid"]
        result = self.validate(route)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid: 1", result.stdout)

    def test_missing_and_unserved_schemas_are_not_skipped(self):
        for kind, version in (("TCPRoute", "v1"), ("TLSRoute", "v1alpha2")):
            with self.subTest(kind=kind, version=version):
                result = self.validate(resource(kind, {}, version))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Errors: 1, Skipped: 0", result.stdout)


if __name__ == "__main__":
    unittest.main()

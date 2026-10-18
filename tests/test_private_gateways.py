import copy
import ipaddress
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / ".cache/cilium-gateway-schemas"


class PrivateGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SCHEMAS.is_dir():
            raise RuntimeError("Run make validate-cilium-gateways before these tests")
        result = subprocess.run(
            ["yq", "-o=json", "-I=0", ".", str(ROOT / ".cache/rendered/system-gateways.yaml")],
            check=True, capture_output=True, text=True, timeout=15,
        )
        cls.resources = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def resources_of_kind(self, kind):
        return [item for item in self.resources if item["kind"] == kind]

    def validate(self, document):
        with tempfile.TemporaryDirectory(prefix="cilium-schema-", dir=ROOT / ".cache") as directory:
            fixture = Path(directory) / "resource.json"
            fixture.write_text(json.dumps(document))
            return subprocess.run(
                ["kubeconform", "-strict", "-summary", "-schema-location",
                 str(SCHEMAS / "{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"), str(fixture)],
                capture_output=True, text=True, timeout=15,
            )

    def test_cilium_gateway_schemas_reject_invalid_admission_configuration(self):
        config = self.resources_of_kind("CiliumGatewayClassConfig")[0]
        pool = self.resources_of_kind("CiliumLoadBalancerIPPool")[0]
        announcement = self.resources_of_kind("CiliumL2AnnouncementPolicy")[0]
        for resource in (config, pool, announcement):
            with self.subTest(kind=resource["kind"], valid=True):
                result = self.validate(resource)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Valid: 1, Invalid: 0, Errors: 0, Skipped: 0", result.stdout)
        invalid_examples = []
        invalid = copy.deepcopy(config)
        invalid["spec"]["service"]["sourceRanges"] = ["0.0.0.0/0"]
        invalid_examples.append(invalid)
        invalid = copy.deepcopy(config)
        invalid["spec"]["service"]["allocateLoadBalancerNodePorts"] = "false"
        invalid_examples.append(invalid)
        invalid = copy.deepcopy(pool)
        invalid["spec"]["serviceSelector"]["matchLabels"] = ["private-home"]
        invalid_examples.append(invalid)
        invalid = copy.deepcopy(announcement)
        invalid["spec"]["interfaces"] = "eno1"
        invalid_examples.append(invalid)
        for invalid in invalid_examples:
            with self.subTest(kind=invalid["kind"], spec=invalid["spec"]):
                result = self.validate(invalid)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Invalid: 1", result.stdout)

    def test_client_admission_excludes_other_lans_nodes_and_pods(self):
        classes = {item["metadata"]["name"]: item for item in self.resources_of_kind("GatewayClass")}
        allowed = {
            "private-home": {"10.0.40.42", "10.0.80.42", "10.0.100.42"},
            "private-admin": {"10.0.80.42", "10.0.100.42"},
        }
        clients = {"10.0.30.42", "10.0.40.42", "10.0.50.42", "10.0.60.42",
                   "10.0.70.11", "10.0.70.42", "10.0.80.42", "10.0.90.42",
                   "10.0.100.42", "10.244.1.42", "192.0.2.42"}
        for config in self.resources_of_kind("CiliumGatewayClassConfig"):
            name = config["metadata"]["name"]
            service = config["spec"]["service"]
            ranges = [ipaddress.ip_network(cidr) for cidr in service["loadBalancerSourceRanges"]]
            admitted = {client for client in clients if any(ipaddress.ip_address(client) in net for net in ranges)}
            self.assertEqual(admitted, allowed[name])
            self.assertFalse(service["allocateLoadBalancerNodePorts"])
            self.assertEqual(service["externalTrafficPolicy"], "Cluster")
            self.assertEqual(service["ipFamilies"], ["IPv4"])
            self.assertEqual(service["ipFamilyPolicy"], "SingleStack")
        for gateway in self.resources_of_kind("Gateway"):
            namespace = gateway["metadata"]["namespace"]
            parameters = classes[gateway["spec"]["gatewayClassName"]]["spec"]["parametersRef"]
            self.assertEqual(parameters["kind"], "CiliumGatewayClassConfig")
            self.assertEqual((parameters["namespace"], parameters["name"]), (namespace, namespace))

    def test_ip_allocation_and_announcements_require_exact_service_identity(self):
        for kind in ("CiliumLoadBalancerIPPool", "CiliumL2AnnouncementPolicy"):
            for resource in self.resources_of_kind(kind):
                name = resource["metadata"]["name"]
                selector = resource["spec"]["serviceSelector"]["matchLabels"]
                self.assertEqual(selector["io.kubernetes.service.namespace"], name)
                self.assertEqual(selector["io.kubernetes.service.name"], f"cilium-gateway-{name}")
                self.assertEqual(selector["gateway.networking.k8s.io/gateway-name"], name)
                if kind == "CiliumL2AnnouncementPolicy":
                    self.assertEqual(resource["spec"]["interfaces"], ["^eno1$"])
                    self.assertFalse(resource["spec"]["externalIPs"])
        addresses = set()
        gateways = {item["metadata"]["name"]: item for item in self.resources_of_kind("Gateway")}
        for pool in self.resources_of_kind("CiliumLoadBalancerIPPool"):
            for block in pool["spec"]["blocks"]:
                self.assertEqual(block["start"], block["stop"])
                addresses.add(block["start"])
                gateway = gateways[pool["metadata"]["name"]]
                self.assertEqual(gateway["spec"]["addresses"], [{"type": "IPAddress", "value": block["start"]}])
        self.assertEqual(addresses, {"10.0.70.200", "10.0.70.201"})

    def test_listener_attachment_is_limited_to_its_application(self):
        expected = {
            "ha.thecavespace.net": ("private-home", "home-assistant"),
            "crafty-controller.thecavespace.net": ("private-admin", "crafty-controller"),
            "argocd.thecavespace.net": ("private-admin", "argocd"),
            "n8n.thecavespace.net": ("private-admin", "n8n"),
            "n8n-webhook.thecavespace.net": ("private-admin", "n8n"),
            "grafana.thecavespace.net": ("private-admin", "monitoring"),
        }
        observed = {}
        for gateway in self.resources_of_kind("Gateway"):
            namespace = gateway["metadata"]["namespace"]
            for listener in gateway["spec"]["listeners"]:
                self.assertEqual(listener["protocol"], "HTTPS")
                self.assertEqual(listener["port"], 443)
                self.assertEqual(listener["tls"]["mode"], "Terminate")
                self.assertEqual(listener["tls"]["certificateRefs"], [
                    {"group": "", "kind": "Secret", "name": f"{namespace}-tls"},
                ])
                namespaces = listener["allowedRoutes"]["namespaces"]
                self.assertEqual(namespaces["from"], "Selector")
                labels = namespaces["selector"]["matchLabels"]
                self.assertEqual(set(labels), {"kubernetes.io/metadata.name"})
                observed[listener["hostname"]] = (namespace, labels["kubernetes.io/metadata.name"])
        self.assertEqual(observed, expected)
        self.assertFalse(self.resources_of_kind("ReferenceGrant"))
        self.assertFalse(self.resources_of_kind("HTTPRoute"))


if __name__ == "__main__":
    unittest.main()

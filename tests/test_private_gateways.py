import copy
import ipaddress
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / ".cache/cilium-gateway-schemas"
ENVOY_SCHEMAS = ROOT / ".cache/envoy-gateway-schemas"


class PrivateGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SCHEMAS.is_dir() or not ENVOY_SCHEMAS.is_dir():
            raise RuntimeError("Run make validate-cilium-gateways validate-envoy-gateway before these tests")
        result = subprocess.run(
            ["yq", "-o=json", "-I=0", "select(. != null)", str(ROOT / ".cache/rendered/system-gateways.yaml")],
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
                 str((ENVOY_SCHEMAS if document["apiVersion"].startswith("gateway.envoyproxy.io/") else SCHEMAS)
                     / "{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"), str(fixture)],
                capture_output=True, text=True, timeout=15,
            )

    def test_schemas_reject_invalid_admission_configuration(self):
        config = self.resources_of_kind("EnvoyProxy")[0]
        pool = self.resources_of_kind("CiliumLoadBalancerIPPool")[0]
        announcement = self.resources_of_kind("CiliumL2AnnouncementPolicy")[0]
        for resource in (config, pool, announcement, self.resources_of_kind("ClientTrafficPolicy")[0]):
            with self.subTest(kind=resource["kind"], valid=True):
                result = self.validate(resource)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Valid: 1, Invalid: 0, Errors: 0, Skipped: 0", result.stdout)
        invalid_examples = []
        invalid = copy.deepcopy(config)
        invalid["spec"]["provider"]["kubernetes"]["envoyService"]["sourceRanges"] = ["0.0.0.0/0"]
        invalid_examples.append(invalid)
        invalid = copy.deepcopy(config)
        invalid["spec"]["provider"]["kubernetes"]["envoyService"]["allocateLoadBalancerNodePorts"] = "false"
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
        for config in self.resources_of_kind("EnvoyProxy"):
            name = config["metadata"]["name"]
            service = config["spec"]["provider"]["kubernetes"]["envoyService"]
            ranges = [ipaddress.ip_network(cidr) for cidr in service["loadBalancerSourceRanges"]]
            admitted = {client for client in clients if any(ipaddress.ip_address(client) in net for net in ranges)}
            self.assertEqual(admitted, allowed[name])
            self.assertFalse(service["allocateLoadBalancerNodePorts"])
            self.assertEqual(service["externalTrafficPolicy"], "Cluster")
            self.assertEqual(config["spec"]["ipFamily"], "IPv4")
        for gateway in self.resources_of_kind("Gateway"):
            namespace = gateway["metadata"]["namespace"]
            parameters = classes[gateway["spec"]["gatewayClassName"]]["spec"]["parametersRef"]
            self.assertEqual(parameters["kind"], "EnvoyProxy")
            self.assertEqual(parameters["group"], "gateway.envoyproxy.io")
            self.assertEqual(classes[gateway["spec"]["gatewayClassName"]]["spec"]["controllerName"],
                             "gateway.envoyproxy.io/gatewayclass-controller")
            self.assertEqual((parameters["namespace"], parameters["name"]), (namespace, namespace))

    def test_ip_allocation_and_announcements_require_exact_service_identity(self):
        for kind in ("CiliumLoadBalancerIPPool", "CiliumL2AnnouncementPolicy"):
            for resource in self.resources_of_kind(kind):
                name = resource["metadata"]["name"]
                selector = resource["spec"]["serviceSelector"]["matchLabels"]
                self.assertEqual(selector["io.kubernetes.service.namespace"], name)
                self.assertEqual(selector["io.kubernetes.service.name"], f"envoy-{name}")
                self.assertEqual(selector["gateway.envoyproxy.io/owning-gateway-name"], name)
                self.assertEqual(selector["gateway.envoyproxy.io/owning-gateway-namespace"], name)
                if kind == "CiliumL2AnnouncementPolicy":
                    self.assertEqual(resource["spec"]["interfaces"], ["^eno1$"])
                    self.assertFalse(resource["spec"]["externalIPs"])
        addresses = set()
        proxies = {item["metadata"]["name"]: item for item in self.resources_of_kind("EnvoyProxy")}
        for pool in self.resources_of_kind("CiliumLoadBalancerIPPool"):
            for block in pool["spec"]["blocks"]:
                self.assertEqual(block["start"], block["stop"])
                addresses.add(block["start"])
                proxy = proxies[pool["metadata"]["name"]]
                service = proxy["spec"]["provider"]["kubernetes"]["envoyService"]
                self.assertEqual(service["annotations"]["lbipam.cilium.io/ips"], block["start"])
                self.assertEqual(service["name"], "envoy-" + pool["metadata"]["name"])
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

    def test_proxies_do_not_trust_client_supplied_forwarding_headers(self):
        policies = self.resources_of_kind("ClientTrafficPolicy")
        self.assertEqual(len(policies), 2)
        for policy in policies:
            namespace = policy["metadata"]["namespace"]
            self.assertEqual(policy["spec"]["targetRefs"], [
                {"group": "gateway.networking.k8s.io", "kind": "Gateway", "name": namespace},
            ])
            detection = policy["spec"]["clientIPDetection"]
            self.assertEqual(detection, {"xForwardedFor": {"numTrustedHops": 0}})
            self.assertEqual(policy["spec"]["tls"]["alpnProtocols"], ["h2", "http/1.1"])

    def test_proxy_images_and_runtime_do_not_require_host_privileges(self):
        for proxy in self.resources_of_kind("EnvoyProxy"):
            provider = proxy["spec"]["provider"]["kubernetes"]
            deployment = provider["envoyDeployment"]
            container = deployment["container"]
            self.assertRegex(container["image"], r":distroless-v1\.39\.3@sha256:[0-9a-f]{64}$")
            self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
            self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
            self.assertTrue(deployment["pod"]["securityContext"]["runAsNonRoot"])
            self.assertGreaterEqual(deployment["replicas"], 2)
            self.assertFalse(proxy["spec"]["mergeGateways"])
            self.assertFalse(any("patch" in value for value in provider.values() if isinstance(value, dict)))

    @staticmethod
    def rendered(name):
        result = subprocess.run(
            ["yq", "-o=json", "-I=0", "select(. != null)", str(ROOT / ".cache/rendered" / name)],
            check=True, capture_output=True, text=True, timeout=15,
        )
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def test_controller_crds_have_one_owner(self):
        controller = self.rendered("helm-envoy-gateway.yaml")
        extensions = self.rendered("helm-envoy-gateway-crds.yaml")
        standard = self.rendered("system-gateway-api-crds.yaml")
        self.assertFalse(any(item["kind"] == "CustomResourceDefinition" for item in controller))
        self.assertGreaterEqual(len(extensions), 2)
        self.assertTrue(all(item["kind"] == "CustomResourceDefinition" and
                            item["spec"]["group"] == "gateway.envoyproxy.io" for item in extensions))
        self.assertTrue(all(item["spec"]["group"] == "gateway.networking.k8s.io" for item in standard))
        self.assertFalse({item["metadata"]["name"] for item in extensions} &
                         {item["metadata"]["name"] for item in standard})

        argocd = self.rendered("system-argocd.yaml")
        apps = [item for item in argocd if item["kind"] == "Application" and
                item["metadata"]["name"] in {"envoy-gateway", "envoy-gateway-crds", "gateways"}]
        self.assertEqual(len(apps), 3)
        for app in apps:
            self.assertNotIn("automated", app["spec"]["syncPolicy"])
            self.assertNotIn("finalizers", app["metadata"])
            self.assertIn("FailOnSharedResource=true", app["spec"]["syncPolicy"]["syncOptions"])
        applications = next(item for item in argocd if item["kind"] == "AppProject" and
                            item["metadata"]["name"] == "applications")
        self.assertFalse(any(item["group"] == "gateway.envoyproxy.io" for item in
                             applications["spec"]["namespaceResourceWhitelist"]))

    def test_controller_can_watch_its_own_endpoints_without_cluster_wide_access(self):
        resources = self.rendered("helm-envoy-gateway.yaml")
        account = {"kind": "ServiceAccount", "name": "envoy-gateway",
                   "namespace": "envoy-gateway-system"}
        roles = {(item["kind"], item["metadata"].get("namespace"), item["metadata"]["name"]): item
                 for item in resources if item["kind"] in {"Role", "ClusterRole"}}
        granted = set()
        for binding in resources:
            if binding["kind"] not in {"RoleBinding", "ClusterRoleBinding"}:
                continue
            if account not in binding.get("subjects", []):
                continue
            ref = binding["roleRef"]
            namespace = binding["metadata"].get("namespace")
            role = roles[(ref["kind"], namespace if ref["kind"] == "Role" else None, ref["name"])]
            for rule in role["rules"]:
                if "discovery.k8s.io" in rule["apiGroups"] and "endpointslices" in rule["resources"]:
                    self.assertEqual(binding["kind"], "RoleBinding")
                    self.assertEqual(set(rule["verbs"]), {"get", "list", "watch"})
                    if namespace == account["namespace"]:
                        granted.update(rule["verbs"])
        self.assertEqual(granted, {"get", "list", "watch"})

    def test_proxies_deny_application_pods_and_have_no_backend_access(self):
        policies = self.rendered("system-network-policies.yaml")
        proxies = [item for item in policies if item["kind"] == "CiliumNetworkPolicy" and
                   item["metadata"]["name"] == "private-proxy"]
        self.assertEqual({item["metadata"]["namespace"] for item in proxies},
                         {"private-home", "private-admin"})
        for policy in proxies:
            self.assertEqual(policy["spec"]["ingressDeny"][0]["fromEndpoints"], [
                {"matchExpressions": [{"key": "k8s:io.kubernetes.pod.namespace", "operator": "Exists"}]},
            ])
            ports = {port["port"] for rule in policy["spec"]["egress"]
                     for to_port in rule["toPorts"] for port in to_port["ports"]}
            self.assertEqual(ports, {"53", "18000"})

    def test_cilium_keeps_the_existing_dataplane_and_host_firewall(self):
        config = next(item for item in self.rendered("helm-cilium.yaml") if
                      item["kind"] == "ConfigMap" and item["metadata"]["name"] == "cilium-config")
        data = config["data"]
        for key in ("kube-proxy-replacement", "enable-host-firewall", "enable-host-legacy-routing",
                    "bpf-lb-sock-hostns-only", "bpf-lb-source-range-all-types", "enable-l2-announcements"):
            self.assertEqual(data[key], "true", key)
        self.assertEqual(data.get("enable-gateway-api", "false"), "false")
        self.assertEqual(data["routing-mode"], "tunnel")


if __name__ == "__main__":
    unittest.main()

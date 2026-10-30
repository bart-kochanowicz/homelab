import json
import subprocess
import tempfile
from pathlib import Path

from .support import ROOT, GatewayTestCase


class GatewayControllerTests(GatewayTestCase):
    def test_controller_crds_have_one_owner(self):
        controller = self.rendered("helm-envoy-gateway.yaml")
        extensions = self.rendered("helm-envoy-gateway-crds.yaml")
        standard = self.rendered("system-gateway-api-crds.yaml")
        self.assertFalse(
            any(item["kind"] == "CustomResourceDefinition" for item in controller)
        )
        self.assertGreaterEqual(len(extensions), 2)
        self.assertTrue(
            all(
                item["kind"] == "CustomResourceDefinition"
                and item["spec"]["group"] == "gateway.envoyproxy.io"
                for item in extensions
            )
        )
        self.assertTrue(
            all(
                item["spec"]["group"] == "gateway.networking.k8s.io"
                for item in standard
            )
        )
        self.assertFalse(
            {item["metadata"]["name"] for item in extensions}
            & {item["metadata"]["name"] for item in standard}
        )

        argocd = self.rendered("system-argocd.yaml")
        apps = [
            item
            for item in argocd
            if item["kind"] == "Application"
            and item["metadata"]["name"]
            in {"envoy-gateway", "envoy-gateway-crds", "gateways"}
        ]
        self.assertEqual(len(apps), 3)
        for app in apps:
            self.assertNotIn("automated", app["spec"]["syncPolicy"])
            self.assertNotIn("finalizers", app["metadata"])
            self.assertIn(
                "FailOnSharedResource=true", app["spec"]["syncPolicy"]["syncOptions"]
            )
        applications = next(
            item
            for item in argocd
            if item["kind"] == "AppProject"
            and item["metadata"]["name"] == "applications"
        )
        self.assertFalse(
            any(
                item["group"] == "gateway.envoyproxy.io"
                for item in applications["spec"]["namespaceResourceWhitelist"]
            )
        )

    def test_controller_can_watch_its_own_endpoints_without_cluster_wide_access(self):
        resources = self.rendered("helm-envoy-gateway.yaml")
        config = next(
            item
            for item in resources
            if item["kind"] == "ConfigMap"
            and item["metadata"]["name"] == "envoy-gateway-config"
        )
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as directory:
            fixture = Path(directory) / "envoy-gateway.yaml"
            fixture.write_text(config["data"]["envoy-gateway.yaml"])
            result = subprocess.run(
                ["yq", "-o=json", ".provider.kubernetes.watch", str(fixture)],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
        watch = json.loads(result.stdout)
        self.assertEqual(watch["type"], "Namespaces")
        self.assertIn("envoy-gateway-system", watch["namespaces"])
        account = {
            "kind": "ServiceAccount",
            "name": "envoy-gateway",
            "namespace": "envoy-gateway-system",
        }
        roles = {
            (
                item["kind"],
                item["metadata"].get("namespace"),
                item["metadata"]["name"],
            ): item
            for item in resources
            if item["kind"] in {"Role", "ClusterRole"}
        }
        granted: set[str] = set()
        for binding in resources:
            if binding["kind"] not in {"RoleBinding", "ClusterRoleBinding"}:
                continue
            if account not in binding.get("subjects", []):
                continue
            ref = binding["roleRef"]
            namespace = binding["metadata"].get("namespace")
            role = roles[
                (ref["kind"], namespace if ref["kind"] == "Role" else None, ref["name"])
            ]
            for rule in role["rules"]:
                if (
                    "discovery.k8s.io" in rule["apiGroups"]
                    and "endpointslices" in rule["resources"]
                ):
                    self.assertEqual(binding["kind"], "RoleBinding")
                    self.assertEqual(set(rule["verbs"]), {"get", "list", "watch"})
                    if namespace == account["namespace"]:
                        granted.update(rule["verbs"])
        self.assertEqual(granted, {"get", "list", "watch"})

    def test_proxies_deny_application_pods_and_limit_backend_access(self):
        policies = self.rendered("system-network-policies.yaml")
        proxies = [
            item
            for item in policies
            if item["kind"] == "CiliumNetworkPolicy"
            and item["metadata"]["name"] == "private-proxy"
        ]
        self.assertEqual(
            {item["metadata"]["namespace"] for item in proxies},
            {"private-home", "private-admin"},
        )
        for policy in proxies:
            self.assertEqual(
                policy["spec"]["ingressDeny"][0]["fromEndpoints"],
                [
                    {
                        "matchExpressions": [
                            {
                                "key": "k8s:io.kubernetes.pod.namespace",
                                "operator": "Exists",
                            }
                        ]
                    },
                ],
            )
            ports = {
                port["port"]
                for rule in policy["spec"]["egress"]
                for to_port in rule["toPorts"]
                for port in to_port["ports"]
            }
            expected_ports = {"53", "18000"}
            if policy["metadata"]["namespace"] == "private-home":
                expected_ports.add("8123")
            else:
                expected_ports.update({"8443", "8080", "5678", "3000"})
            self.assertEqual(ports, expected_ports)
            self.assertEqual(set(policy["spec"]["ingress"][0]), {"fromCIDR", "toPorts"})
            self.assertEqual(len(policy["spec"]["ingress"]), 1)

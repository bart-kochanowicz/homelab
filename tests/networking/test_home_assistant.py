import json
import subprocess
import tempfile
from pathlib import Path

from .support import ROOT, GatewayTestCase


class HomeAssistantGatewayTests(GatewayTestCase):
    def test_home_assistant_route_only_uses_its_private_home_listener_and_service(self):
        resources = self.rendered("apps-home-assistant.yaml")
        routes = [item for item in resources if item["kind"] == "HTTPRoute"]
        self.assertEqual(len(routes), 1)
        route = routes[0]
        self.assertEqual(route["metadata"]["namespace"], "home-assistant")
        spec = route["spec"]
        self.assertEqual(
            spec["parentRefs"],
            [
                {
                    "name": "private-home",
                    "namespace": "private-home",
                    "sectionName": "home-assistant",
                }
            ],
        )
        self.assertEqual(spec["hostnames"], ["ha.thecavespace.net"])
        self.assertEqual(len(spec["rules"]), 1)
        rule = spec["rules"][0]
        self.assertEqual(set(rule), {"matches", "backendRefs", "timeouts"})
        self.assertEqual(
            rule["matches"], [{"path": {"type": "PathPrefix", "value": "/"}}]
        )
        self.assertEqual(
            rule["backendRefs"], [{"name": "home-assistant", "port": 8123}]
        )
        self.assertEqual(rule["timeouts"], {"request": "0s"})
        service = next(
            item
            for item in resources
            if item["kind"] == "Service"
            and item["metadata"]["name"] == rule["backendRefs"][0]["name"]
        )
        self.assertEqual(
            service["metadata"]["namespace"], route["metadata"]["namespace"]
        )
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertIn(
            {"name": "https", "port": 8123, "targetPort": 8123, "protocol": "TCP"},
            service["spec"]["ports"],
        )

    def test_home_assistant_backend_tls_matches_the_mounted_certificate_and_probes(
        self,
    ):
        resources = self.rendered("apps-home-assistant.yaml")
        certificate = next(item for item in resources if item["kind"] == "Certificate")
        policy = next(item for item in resources if item["kind"] == "BackendTLSPolicy")
        service = next(item for item in resources if item["kind"] == "Service")
        deployment = next(item for item in resources if item["kind"] == "Deployment")
        config = next(item for item in resources if item["kind"] == "ConfigMap")
        self.assertEqual(
            policy["spec"]["targetRefs"],
            [
                {
                    "group": "",
                    "kind": "Service",
                    "name": service["metadata"]["name"],
                    "sectionName": service["spec"]["ports"][0]["name"],
                }
            ],
        )
        self.assertEqual(
            policy["spec"]["validation"],
            {
                "hostname": "ha.thecavespace.net",
                "wellKnownCACertificates": "System",
            },
        )
        self.assertEqual(
            set(certificate["spec"]["dnsNames"]),
            {
                policy["spec"]["validation"]["hostname"],
                "ha-backend.thecavespace.net",
            },
        )
        self.assertEqual(
            certificate["spec"]["issuerRef"]["name"], "letsencrypt-production"
        )
        self.assertEqual(certificate["spec"]["privateKey"]["rotationPolicy"], "Always")
        self.assertLess(
            int(certificate["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]),
            int(policy["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]),
        )
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]
        mount = next(
            item for item in container["volumeMounts"] if item["name"] == "backend-tls"
        )
        self.assertTrue(mount["readOnly"])
        self.assertFalse({"subPath", "subPathExpr"} & set(mount))
        volume = next(item for item in pod["volumes"] if item["name"] == mount["name"])
        secret = certificate["spec"]["secretName"]
        self.assertEqual(volume["secret"], {"secretName": secret, "defaultMode": 0o400})
        self.assertEqual(
            deployment["metadata"]["annotations"][
                "secret.reloader.stakater.com/reload"
            ],
            secret,
        )
        self.assertEqual(deployment["spec"]["strategy"], {"type": "Recreate"})
        for probe in ("livenessProbe", "readinessProbe"):
            self.assertEqual(container[probe]["httpGet"]["scheme"], "HTTPS")
            port = next(
                item
                for item in container["ports"]
                if item["name"] == container[probe]["httpGet"]["port"]
            )
            self.assertEqual(
                port["containerPort"], service["spec"]["ports"][0]["targetPort"]
            )
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as directory:
            fixture = Path(directory) / "configuration.yaml"
            fixture.write_text(config["data"]["configuration.yaml"])
            result = subprocess.run(
                ["yq", "-o=json", ".http", str(fixture)],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
        http = json.loads(result.stdout)
        self.assertEqual(http["ssl_certificate"], mount["mountPath"] + "/tls.crt")
        self.assertEqual(http["ssl_key"], mount["mountPath"] + "/tls.key")

    def test_home_assistant_host_access_requires_home_proxy_identity(self):
        policies = self.rendered("system-network-policies.yaml")
        host = next(
            item
            for item in policies
            if item["kind"] == "CiliumClusterwideNetworkPolicy"
            and item["metadata"]["name"] == "homelab-host-firewall"
        )
        proxy_rules = [
            rule
            for rule in host["spec"]["ingress"]
            if any(
                selector.get("matchLabels", {}).get("k8s:io.kubernetes.pod.namespace")
                == "private-home"
                for selector in rule.get("fromEndpoints", [])
            )
        ]
        self.assertEqual(len(proxy_rules), 1)
        rule = proxy_rules[0]
        self.assertEqual(set(rule), {"fromEndpoints", "toPorts"})
        self.assertEqual(
            rule["fromEndpoints"],
            [
                {
                    "matchLabels": {
                        "k8s:io.kubernetes.pod.namespace": "private-home",
                        "k8s:app.kubernetes.io/managed-by": "envoy-gateway",
                        "k8s:app.kubernetes.io/component": "proxy",
                        "k8s:gateway.envoyproxy.io/owning-gateway-name": "private-home",
                    }
                }
            ],
        )
        ports = [{"ports": [{"port": "8123", "protocol": "TCP"}]}]
        self.assertEqual(rule["toPorts"], ports)
        home = next(
            item
            for item in policies
            if item["kind"] == "CiliumNetworkPolicy"
            and item["metadata"]["name"] == "private-proxy"
            and item["metadata"]["namespace"] == "private-home"
        )
        self.assertEqual(
            home["spec"]["endpointSelector"],
            {
                "matchLabels": {
                    "app.kubernetes.io/managed-by": "envoy-gateway",
                    "app.kubernetes.io/component": "proxy",
                    "gateway.envoyproxy.io/owning-gateway-name": "private-home",
                }
            },
        )
        node_rules = [rule for rule in home["spec"]["egress"] if "toEntities" in rule]
        self.assertEqual(
            node_rules, [{"toEntities": ["host", "remote-node"], "toPorts": ports}]
        )

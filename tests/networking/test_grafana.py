import configparser
import ipaddress
from urllib.parse import urlsplit

from .support import GatewayTestCase


class GrafanaGatewayTests(GatewayTestCase):
    def test_grafana_route_uses_only_admin_listener_and_verified_backend(self):
        resources = self.rendered("system-monitoring.yaml")
        route = next(item for item in resources if item["kind"] == "HTTPRoute")
        policy = next(item for item in resources if item["kind"] == "BackendTLSPolicy")
        certificate = next(item for item in resources if item["kind"] == "Certificate")
        service = next(
            item
            for item in resources
            if item["kind"] == "Service"
            and item["metadata"]["name"] == "kube-prometheus-stack-grafana"
        )
        config = next(
            item
            for item in resources
            if item["kind"] == "ConfigMap" and "grafana.ini" in item.get("data", {})
        )
        settings = configparser.ConfigParser(interpolation=None)
        settings.read_string(config["data"]["grafana.ini"])
        hostname = urlsplit(settings["server"]["root_url"]).hostname
        self.assertEqual(
            route["metadata"]["namespace"], service["metadata"]["namespace"]
        )
        self.assertEqual(route["spec"]["hostnames"], [hostname])
        self.assertEqual(
            route["spec"]["parentRefs"],
            [
                {
                    "group": "gateway.networking.k8s.io",
                    "kind": "Gateway",
                    "name": "private-admin",
                    "namespace": "private-admin",
                    "sectionName": "grafana",
                }
            ],
        )
        self.assertEqual(
            route["spec"]["rules"],
            [
                {
                    "matches": [{"path": {"type": "PathPrefix", "value": "/"}}],
                    "backendRefs": [
                        {
                            "group": "",
                            "kind": "Service",
                            "weight": 1,
                            "name": service["metadata"]["name"],
                            "port": service["spec"]["ports"][0]["port"],
                        }
                    ],
                    "timeouts": {"request": "0s"},
                }
            ],
        )
        self.assertEqual(
            policy["metadata"]["namespace"], service["metadata"]["namespace"]
        )
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
                "hostname": "grafana-backend.thecavespace.net",
                "wellKnownCACertificates": "System",
            },
        )
        self.assertIn(
            policy["spec"]["validation"]["hostname"], certificate["spec"]["dnsNames"]
        )
        self.assertLess(
            int(certificate["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]),
            int(policy["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]),
        )
        self.assertLess(
            int(policy["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]), 0
        )

    def test_grafana_tls_preserves_verified_scraping_and_local_provisioning(self):
        resources = self.rendered("system-monitoring.yaml")
        deployment = next(
            item
            for item in resources
            if item["kind"] == "Deployment"
            and item["metadata"]["name"] == "kube-prometheus-stack-grafana"
        )
        certificate = next(
            item
            for item in resources
            if item["kind"] == "Certificate"
            and item["metadata"]["name"] == "grafana-backend"
        )
        config = next(
            item
            for item in resources
            if item["kind"] == "ConfigMap" and "grafana.ini" in item.get("data", {})
        )
        settings = configparser.ConfigParser(interpolation=None)
        settings.read_string(config["data"]["grafana.ini"])
        self.assertEqual(settings["server"]["protocol"], "https")
        self.assertEqual(
            settings["server"]["root_url"], "https://grafana.thecavespace.net/"
        )
        self.assertEqual(settings["server"]["certs_watch_interval"], "30s")
        self.assertTrue(settings.getboolean("security", "cookie_secure"))
        pod = deployment["spec"]["template"]["spec"]
        grafana = next(item for item in pod["containers"] if item["name"] == "grafana")
        mount = next(
            item for item in grafana["volumeMounts"] if item["name"] == "backend-tls"
        )
        self.assertTrue(mount["readOnly"])
        self.assertFalse(mount.get("subPath") or mount.get("subPathExpr"))
        volume = next(item for item in pod["volumes"] if item["name"] == mount["name"])
        self.assertEqual(
            volume["secret"],
            {"secretName": certificate["spec"]["secretName"], "defaultMode": 0o440},
        )
        self.assertEqual(pod["securityContext"]["fsGroup"], 472)
        claims = [
            item
            for item in resources
            if item["kind"] == "PersistentVolumeClaim"
            and item["metadata"]["labels"].get("app.kubernetes.io/name") == "grafana"
        ]
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim["spec"]["storageClassName"], "local-path-nvme")
        self.assertEqual(
            claim["metadata"]["annotations"]["argocd.argoproj.io/sync-options"],
            "Prune=false,Delete=false",
        )
        self.assertIn(
            {
                "name": "storage",
                "persistentVolumeClaim": {"claimName": claim["metadata"]["name"]},
            },
            pod["volumes"],
        )
        backup = next(
            item
            for item in self.rendered("system-backups.yaml")
            if item["kind"] == "PreBackupPod"
            and item["metadata"]["namespace"] == "monitoring"
        )
        source = next(
            item
            for item in backup["spec"]["pod"]["spec"]["volumes"]
            if item["name"] == "data"
        )
        self.assertEqual(
            source["persistentVolumeClaim"]["claimName"], claim["metadata"]["name"]
        )
        for key, filename in (("cert_file", "tls.crt"), ("cert_key", "tls.key")):
            self.assertEqual(
                settings["server"][key], f"{mount['mountPath']}/{filename}"
            )
        self.assertEqual(deployment["spec"]["strategy"], {"type": "Recreate"})
        for probe in ("readinessProbe", "livenessProbe"):
            self.assertEqual(
                grafana[probe]["httpGet"],
                {
                    "path": "/api/health",
                    "port": 3000,
                    "scheme": "HTTPS",
                },
            )
        service = next(
            item
            for item in resources
            if item["kind"] == "Service"
            and item["metadata"]["name"] == deployment["metadata"]["name"]
        )
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        port = service["spec"]["ports"][0]
        self.assertEqual((port["port"], port["appProtocol"]), (3000, "https"))
        monitor = next(
            item
            for item in resources
            if item["kind"] == "ServiceMonitor"
            and item["metadata"]["name"] == service["metadata"]["name"]
        )
        prometheus = next(item for item in resources if item["kind"] == "Prometheus")
        selected = prometheus["spec"]["serviceMonitorSelector"]["matchLabels"]
        self.assertTrue(selected.items() <= monitor["metadata"]["labels"].items())
        endpoint = monitor["spec"]["endpoints"][0]
        self.assertEqual(
            (endpoint["port"], endpoint["scheme"]), (port["name"], "https")
        )
        self.assertEqual(
            endpoint["tlsConfig"], {"serverName": "grafana-backend.thecavespace.net"}
        )
        backend = endpoint["tlsConfig"]["serverName"]
        self.assertIn(backend, certificate["spec"]["dnsNames"])
        self.assertIn({"ip": "127.0.0.1", "hostnames": [backend]}, pod["hostAliases"])
        for name, kind in (
            ("grafana-sc-dashboard", "dashboards"),
            ("grafana-sc-datasources", "datasources"),
        ):
            container = next(item for item in pod["containers"] if item["name"] == name)
            env = {item["name"]: item.get("value") for item in container["env"]}
            self.assertEqual(
                env["REQ_URL"],
                f"https://{backend}:3000/api/admin/provisioning/{kind}/reload",
            )
            self.assertNotEqual(env.get("REQ_SKIP_TLS_VERIFY", "false").lower(), "true")

    def test_grafana_ingress_preserves_scraping_and_excludes_other_clients(self):
        policies = self.rendered("system-network-policies.yaml")
        grafana = next(
            item
            for item in policies
            if item["kind"] == "NetworkPolicy"
            and item["metadata"]["name"] == "grafana-server"
        )
        admin = next(
            item
            for item in policies
            if item["kind"] == "CiliumNetworkPolicy"
            and item["metadata"]["name"] == "private-proxy"
            and item["metadata"]["namespace"] == "private-admin"
        )
        self.assertEqual(grafana["metadata"]["namespace"], "monitoring")
        deployment = next(
            item
            for item in self.rendered("system-monitoring.yaml")
            if item["kind"] == "Deployment"
            and item["metadata"]["name"] == "kube-prometheus-stack-grafana"
        )
        self.assertEqual(grafana["spec"]["podSelector"], deployment["spec"]["selector"])
        self.assertEqual(grafana["spec"]["policyTypes"], ["Ingress"])
        self.assertNotIn("egress", grafana["spec"])

        def allows(
            namespace: str, labels: dict[str, str], address: str, port: int
        ) -> bool:
            for rule in grafana["spec"]["ingress"]:
                if {"port": port, "protocol": "TCP"} not in rule["ports"]:
                    continue
                for peer in rule["from"]:
                    if "ipBlock" in peer:
                        if ipaddress.ip_address(address) in ipaddress.ip_network(
                            peer["ipBlock"]["cidr"]
                        ):
                            return True
                    else:
                        expected_namespace = peer["namespaceSelector"]["matchLabels"][
                            "kubernetes.io/metadata.name"
                        ]
                        expected_labels = peer["podSelector"]["matchLabels"]
                        if (
                            namespace == expected_namespace
                            and expected_labels.items() <= labels.items()
                        ):
                            return True
            return False

        proxy = admin["spec"]["endpointSelector"]["matchLabels"]
        prometheus = {
            "app.kubernetes.io/name": "prometheus",
            "operator.prometheus.io/name": "kube-prometheus-stack-prometheus",
        }
        cases = [
            ("private-admin", proxy, "10.244.1.10", 3000, True),
            ("private-home", proxy, "10.244.1.10", 3000, False),
            ("private-admin", {}, "10.244.1.10", 3000, False),
            ("monitoring", prometheus, "10.244.1.10", 3000, True),
            ("n8n", prometheus, "10.244.1.10", 3000, False),
            (
                "monitoring",
                {"app.kubernetes.io/name": "alertmanager"},
                "10.244.1.10",
                3000,
                False,
            ),
            ("private-admin", proxy, "10.244.1.10", 6060, False),
            ("monitoring", prometheus, "10.244.1.10", 9094, False),
            (None, {}, "10.0.80.42", 3000, True),
            (None, {}, "10.0.100.42", 3000, True),
            (None, {}, "10.0.40.42", 3000, False),
            (None, {}, "192.0.2.42", 3000, False),
        ]
        for namespace, labels, address, port, expected in cases:
            with self.subTest(
                namespace=namespace, labels=labels, address=address, port=port
            ):
                self.assertEqual(allows(namespace, labels, address, port), expected)
        egress = [
            rule
            for rule in admin["spec"]["egress"]
            if any(
                port["port"] == "3000"
                for block in rule["toPorts"]
                for port in block["ports"]
            )
        ]
        self.assertEqual(
            egress,
            [
                {
                    "toEndpoints": [
                        {
                            "matchLabels": {
                                "k8s:io.kubernetes.pod.namespace": "monitoring",
                                "k8s:app.kubernetes.io/instance": "kube-prometheus-stack",
                                "k8s:app.kubernetes.io/name": "grafana",
                            }
                        }
                    ],
                    "toPorts": [{"ports": [{"port": "3000", "protocol": "TCP"}]}],
                }
            ],
        )

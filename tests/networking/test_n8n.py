from urllib.parse import urlsplit

from .support import GatewayTestCase


class N8nGatewayTests(GatewayTestCase):
    def test_n8n_native_tls_preserves_identity_data_and_certificate_projection(self):
        resources = self.rendered("apps-n8n.yaml")
        deployment = next(item for item in resources if item["kind"] == "Deployment")
        certificate = next(item for item in resources if item["kind"] == "Certificate")
        service = next(item for item in resources if item["kind"] == "Service")
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]
        env = {item["name"]: item for item in container["env"]}
        mount = next(
            item for item in container["volumeMounts"] if item["name"] == "backend-tls"
        )
        self.assertTrue(mount["readOnly"])
        self.assertFalse({"subPath", "subPathExpr"} & set(mount))
        volume = next(item for item in pod["volumes"] if item["name"] == mount["name"])
        self.assertEqual(
            volume["secret"],
            {"secretName": certificate["spec"]["secretName"], "defaultMode": 0o440},
        )
        self.assertEqual(pod["securityContext"]["fsGroup"], 1000)
        self.assertEqual(env["N8N_SSL_CERT"]["value"], mount["mountPath"] + "/tls.crt")
        self.assertEqual(env["N8N_SSL_KEY"]["value"], mount["mountPath"] + "/tls.key")
        self.assertEqual(certificate["spec"]["dnsNames"], [env["N8N_HOST"]["value"]])
        self.assertEqual(
            certificate["spec"]["issuerRef"]["name"], "letsencrypt-production"
        )
        self.assertEqual(env["N8N_PROTOCOL"]["value"], "https")
        self.assertEqual(env["N8N_PROXY_HOPS"]["value"], "1")
        self.assertEqual(
            env["N8N_ENCRYPTION_KEY"]["valueFrom"],
            {
                "secretKeyRef": {"name": "n8n-secret", "key": "N8N_ENCRYPTION_KEY"},
            },
        )
        claim = next(
            item for item in resources if item["kind"] == "PersistentVolumeClaim"
        )
        self.assertEqual(claim["spec"]["storageClassName"], "local-path-nvme")
        self.assertIn(
            {
                "name": "n8n-data",
                "persistentVolumeClaim": {"claimName": claim["metadata"]["name"]},
            },
            pod["volumes"],
        )
        backup = next(
            item
            for item in self.rendered("system-backups.yaml")
            if item["kind"] == "PreBackupPod" and item["metadata"]["namespace"] == "n8n"
        )
        source = next(
            item
            for item in backup["spec"]["pod"]["spec"]["volumes"]
            if item["name"] == "data"
        )
        self.assertEqual(
            source["persistentVolumeClaim"]["claimName"], claim["metadata"]["name"]
        )
        self.assertEqual(
            deployment["metadata"]["annotations"][
                "secret.reloader.stakater.com/reload"
            ],
            certificate["spec"]["secretName"],
        )
        self.assertEqual(deployment["spec"]["strategy"], {"type": "Recreate"})
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertEqual(
            service["spec"]["ports"],
            [
                {
                    "name": "https",
                    "port": 5678,
                    "targetPort": 5678,
                    "protocol": "TCP",
                }
            ],
        )
        for name in ("startupProbe", "livenessProbe", "readinessProbe"):
            self.assertEqual(
                container[name]["httpGet"],
                {"path": "/healthz", "port": "https", "scheme": "HTTPS"},
            )
        self.assertIn(
            {"name": "https", "containerPort": 5678, "protocol": "TCP"},
            container["ports"],
        )

    def test_n8n_routes_match_application_urls_and_require_verified_admin_backend_tls(
        self,
    ):
        resources = self.rendered("apps-n8n.yaml")
        routes = {
            item["metadata"]["name"]: item
            for item in resources
            if item["kind"] == "HTTPRoute"
        }
        deployment = next(item for item in resources if item["kind"] == "Deployment")
        service = next(item for item in resources if item["kind"] == "Service")
        certificate = next(item for item in resources if item["kind"] == "Certificate")
        policy = next(item for item in resources if item["kind"] == "BackendTLSPolicy")
        env = {
            item["name"]: item.get("value")
            for item in deployment["spec"]["template"]["spec"]["containers"][0]["env"]
        }
        editor_url: str = env["N8N_EDITOR_BASE_URL"]
        webhook_url: str = env["WEBHOOK_URL"]
        hosts = {
            "n8n": urlsplit(editor_url).hostname,
            "n8n-webhook": urlsplit(webhook_url).hostname,
        }
        self.assertEqual(set(routes), set(hosts))
        for name, route in routes.items():
            with self.subTest(route=name):
                self.assertEqual(route["metadata"]["namespace"], "n8n")
                self.assertEqual(route["spec"]["hostnames"], [hosts[name]])
                self.assertEqual(
                    route["spec"]["parentRefs"],
                    [
                        {
                            "name": "private-admin",
                            "namespace": "private-admin",
                            "sectionName": name,
                        }
                    ],
                )
                self.assertEqual(
                    route["spec"]["rules"],
                    [
                        {
                            "matches": [{"path": {"type": "PathPrefix", "value": "/"}}],
                            "backendRefs": [
                                {"name": service["metadata"]["name"], "port": 5678}
                            ],
                            "timeouts": {"request": "0s"},
                        }
                    ],
                )
        self.assertEqual(service["metadata"]["namespace"], "n8n")
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertEqual(policy["metadata"]["namespace"], "n8n")
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
                "hostname": env["N8N_HOST"],
                "wellKnownCACertificates": "System",
            },
        )
        self.assertEqual(certificate["spec"]["dnsNames"], [env["N8N_HOST"]])
        self.assertLess(
            int(certificate["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]),
            int(policy["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]),
        )
        self.assertLess(
            int(policy["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]), 0
        )

    def test_n8n_access_requires_admin_proxy_and_preserves_management(self):
        policies = self.rendered("system-network-policies.yaml")
        app = next(
            item
            for item in policies
            if item["kind"] == "NetworkPolicy"
            and item["metadata"]["name"] == "allow-n8n"
        )
        admin = next(
            item
            for item in policies
            if item["kind"] == "CiliumNetworkPolicy"
            and item["metadata"]["name"] == "private-proxy"
            and item["metadata"]["namespace"] == "private-admin"
        )
        self.assertEqual(app["metadata"]["namespace"], "n8n")
        self.assertEqual(
            app["spec"]["podSelector"],
            {"matchLabels": {"app.kubernetes.io/name": "n8n"}},
        )
        pod_ingress = [
            rule
            for rule in app["spec"]["ingress"]
            if any(
                "namespaceSelector" in peer or "podSelector" in peer
                for peer in rule["from"]
            )
        ]
        self.assertEqual(
            pod_ingress,
            [
                {
                    "from": [
                        {
                            "namespaceSelector": {
                                "matchLabels": {
                                    "kubernetes.io/metadata.name": "private-admin"
                                }
                            },
                            "podSelector": {
                                "matchLabels": admin["spec"]["endpointSelector"][
                                    "matchLabels"
                                ]
                            },
                        }
                    ],
                    "ports": [{"protocol": "TCP", "port": 5678}],
                }
            ],
        )
        self.assertEqual(
            [rule for rule in app["spec"]["ingress"] if rule not in pod_ingress],
            [
                {
                    "from": [
                        {"ipBlock": {"cidr": cidr}}
                        for cidr in ("10.0.80.0/24", "10.0.100.0/24")
                    ],
                    "ports": [{"protocol": "TCP", "port": 5678}],
                }
            ],
        )
        egress = [
            rule
            for rule in admin["spec"]["egress"]
            if any(
                port["port"] == "5678"
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
                                "k8s:io.kubernetes.pod.namespace": "n8n",
                                "k8s:app.kubernetes.io/name": "n8n",
                            }
                        }
                    ],
                    "toPorts": [{"ports": [{"port": "5678", "protocol": "TCP"}]}],
                }
            ],
        )

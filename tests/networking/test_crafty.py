from .support import GatewayTestCase


class CraftyGatewayTests(GatewayTestCase):
    def test_crafty_admin_route_requires_verified_tls_on_the_panel_port(self):
        resources = self.rendered("apps-crafty-controller.yaml")
        route = next(item for item in resources if item["kind"] == "HTTPRoute")
        namespace = route["metadata"]["namespace"]
        self.assertEqual(namespace, "crafty-controller")
        self.assertEqual(
            route["spec"]["parentRefs"],
            [
                {
                    "name": "private-admin",
                    "namespace": "private-admin",
                    "sectionName": "crafty-controller",
                }
            ],
        )
        self.assertEqual(
            route["spec"]["hostnames"], ["crafty-controller.thecavespace.net"]
        )
        self.assertEqual(len(route["spec"]["rules"]), 1)
        rule = route["spec"]["rules"][0]
        self.assertEqual(
            rule,
            {
                "matches": [{"path": {"type": "PathPrefix", "value": "/"}}],
                "backendRefs": [{"name": "crafty-controller", "port": 8443}],
                "timeouts": {"request": "0s"},
            },
        )
        service = next(
            item
            for item in resources
            if item["kind"] == "Service"
            and item["metadata"]["name"] == rule["backendRefs"][0]["name"]
        )
        port = next(
            item
            for item in service["spec"]["ports"]
            if item["port"] == rule["backendRefs"][0]["port"]
        )
        policy = next(item for item in resources if item["kind"] == "BackendTLSPolicy")
        self.assertEqual(policy["metadata"]["namespace"], namespace)
        self.assertEqual(service["metadata"]["namespace"], namespace)
        self.assertEqual(
            policy["spec"]["targetRefs"],
            [
                {
                    "group": "",
                    "kind": "Service",
                    "name": service["metadata"]["name"],
                    "sectionName": port["name"],
                }
            ],
        )
        certificate = next(item for item in resources if item["kind"] == "Certificate")
        validation = policy["spec"]["validation"]
        self.assertEqual(
            validation,
            {
                "hostname": route["spec"]["hostnames"][0],
                "wellKnownCACertificates": "System",
            },
        )
        self.assertEqual(certificate["spec"]["dnsNames"], [validation["hostname"]])
        self.assertLess(
            int(certificate["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]),
            int(policy["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]),
        )
        self.assertLess(
            int(policy["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]),
            int(
                route["metadata"]
                .get("annotations", {})
                .get("argocd.argoproj.io/sync-wave", 0)
            ),
        )

    def test_crafty_certificate_projection_can_receive_renewed_key_pairs(self):
        resources = self.rendered("apps-crafty-controller.yaml")
        certificate = next(item for item in resources if item["kind"] == "Certificate")
        self.assertEqual(
            certificate["spec"]["issuerRef"],
            {
                "name": "letsencrypt-production",
                "kind": "ClusterIssuer",
                "group": "cert-manager.io",
            },
        )
        self.assertEqual(certificate["spec"]["privateKey"]["rotationPolicy"], "Always")
        deployment = next(item for item in resources if item["kind"] == "Deployment")
        pod = deployment["spec"]["template"]["spec"]
        mount = next(
            item
            for item in pod["containers"][0]["volumeMounts"]
            if item["mountPath"] == "/crafty/app/config/web/certs"
        )
        self.assertTrue(mount["readOnly"])
        self.assertFalse({"subPath", "subPathExpr"} & set(mount))
        volume = next(item for item in pod["volumes"] if item["name"] == mount["name"])
        self.assertEqual(
            volume["secret"],
            {
                "secretName": certificate["spec"]["secretName"],
                "defaultMode": 0o440,
                "items": [
                    {"key": "tls.crt", "path": "commander.cert.pem"},
                    {"key": "tls.key", "path": "commander.key.pem"},
                ],
            },
        )

    def test_crafty_panel_access_requires_admin_proxy_and_exact_backend(self):
        policies = self.rendered("system-network-policies.yaml")
        crafty = next(
            item
            for item in policies
            if item["kind"] == "NetworkPolicy"
            and item["metadata"]["namespace"] == "crafty-controller"
            and item["metadata"]["name"] == "allow-crafty"
        )
        self.assertEqual(
            crafty["spec"]["podSelector"],
            {
                "matchLabels": {"app.kubernetes.io/name": "crafty-controller"},
            },
        )
        proxy_ingress = [
            rule
            for rule in crafty["spec"]["ingress"]
            if any(
                "namespaceSelector" in peer or "podSelector" in peer
                for peer in rule["from"]
            )
        ]
        self.assertEqual(
            proxy_ingress,
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
                                "matchLabels": {
                                    "app.kubernetes.io/managed-by": "envoy-gateway",
                                    "app.kubernetes.io/component": "proxy",
                                    "gateway.envoyproxy.io/owning-gateway-name": "private-admin",
                                }
                            },
                        }
                    ],
                    "ports": [{"protocol": "TCP", "port": 8443}],
                }
            ],
        )
        admin = next(
            item
            for item in policies
            if item["kind"] == "CiliumNetworkPolicy"
            and item["metadata"]["name"] == "private-proxy"
            and item["metadata"]["namespace"] == "private-admin"
        )
        self.assertEqual(
            admin["spec"]["endpointSelector"],
            {
                "matchLabels": proxy_ingress[0]["from"][0]["podSelector"][
                    "matchLabels"
                ],
            },
        )
        backend_rules = [
            rule
            for rule in admin["spec"]["egress"]
            if any(
                port["port"] == "8443"
                for block in rule["toPorts"]
                for port in block["ports"]
            )
        ]
        self.assertEqual(
            backend_rules,
            [
                {
                    "toEndpoints": [
                        {
                            "matchLabels": {
                                "k8s:io.kubernetes.pod.namespace": "crafty-controller",
                                "k8s:app.kubernetes.io/name": "crafty-controller",
                            }
                        }
                    ],
                    "toPorts": [{"ports": [{"port": "8443", "protocol": "TCP"}]}],
                }
            ],
        )

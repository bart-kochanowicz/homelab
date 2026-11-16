from .support import GatewayTestCase


class SealedSecretsWebTests(GatewayTestCase):
    def test_ui_cannot_read_secrets_and_is_restricted_to_controller_proxy(self):
        resources = self.rendered("system-sealed-secrets-web.yaml")
        self.assertFalse(
            any(
                item["kind"] in {"ClusterRole", "ClusterRoleBinding"}
                for item in resources
            )
        )
        role = next(item for item in resources if item["kind"] == "Role")
        rules = {rule["resources"][0]: rule for rule in role["rules"]}
        self.assertEqual(set(rules), {"services", "services/proxy"})
        self.assertEqual(
            rules["services"]["resourceNames"], ["sealed-secrets-controller"]
        )
        self.assertEqual(set(rules["services"]["verbs"]), {"get"})
        self.assertEqual(
            set(rules["services/proxy"]["resourceNames"]),
            {"sealed-secrets-controller", "http:sealed-secrets-controller:http"},
        )
        self.assertEqual(set(rules["services/proxy"]["verbs"]), {"get", "create"})
        deployment = next(item for item in resources if item["kind"] == "Deployment")
        pod = deployment["spec"]["template"]["spec"]
        self.assertEqual(pod["serviceAccountName"], "sealed-secrets-web")
        self.assertIn("--disable-load-secrets", pod["containers"][0]["args"])
        policy = next(
            item
            for item in self.rendered("system-network-policies.yaml")
            if item["kind"] == "NetworkPolicy"
            and item["metadata"]["name"] == "sealed-secrets-web"
        )
        self.assertEqual(
            policy["spec"]["podSelector"]["matchLabels"],
            deployment["spec"]["selector"]["matchLabels"],
        )
        self.assertEqual(policy["spec"]["policyTypes"], ["Ingress"])
        self.assertEqual(
            policy["spec"]["ingress"],
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
            for item in self.rendered("system-network-policies.yaml")
            if item["kind"] == "CiliumNetworkPolicy"
            and item["metadata"]["name"] == "private-proxy"
            and item["metadata"]["namespace"] == "private-admin"
        )
        self.assertEqual(
            admin["spec"]["endpointSelector"]["matchLabels"],
            policy["spec"]["ingress"][0]["from"][0]["podSelector"]["matchLabels"],
        )
        backend_rules = [
            rule
            for rule in admin["spec"]["egress"]
            if any(
                endpoint.get("matchLabels", {}).get("k8s:io.kubernetes.pod.namespace")
                == "sealed-secrets"
                for endpoint in rule.get("toEndpoints", [])
            )
        ]
        self.assertEqual(
            backend_rules,
            [
                {
                    "toEndpoints": [
                        {
                            "matchLabels": {
                                "k8s:io.kubernetes.pod.namespace": "sealed-secrets",
                                "k8s:app.kubernetes.io/name": "sealed-secrets-web",
                            }
                        }
                    ],
                    "toPorts": [{"ports": [{"port": "8443", "protocol": "TCP"}]}],
                }
            ],
        )
        self.assertFalse(pod["automountServiceAccountToken"])
        containers = {container["name"]: container for container in pod["containers"]}
        self.assertNotIn(
            "kubernetes-api-access",
            [mount["name"] for mount in containers["tls-proxy"]["volumeMounts"]],
        )
        route = next(item for item in resources if item["kind"] == "HTTPRoute")
        backend_tls = next(
            item for item in resources if item["kind"] == "BackendTLSPolicy"
        )
        service = next(item for item in resources if item["kind"] == "Service")
        for dependency in (service, route):
            wave = int(
                dependency["metadata"]
                .get("annotations", {})
                .get("argocd.argoproj.io/sync-wave", "0")
            )
            policy_wave = int(
                backend_tls["metadata"]
                .get("annotations", {})
                .get("argocd.argoproj.io/sync-wave", "0")
            )
            self.assertLessEqual(wave, policy_wave)
        self.assertEqual(
            route["spec"]["hostnames"], ["sealed-secrets.thecavespace.net"]
        )
        self.assertEqual(
            backend_tls["spec"]["validation"],
            {
                "hostname": "sealed-secrets.thecavespace.net",
                "wellKnownCACertificates": "System",
            },
        )

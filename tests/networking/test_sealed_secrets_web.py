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

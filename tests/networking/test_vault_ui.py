from .support import GatewayTestCase


class VaultUITests(GatewayTestCase):
    def test_private_route_validates_backend_tls(self):
        resources = self.rendered("helm-vault.yaml")
        route = next(item for item in resources if item["kind"] == "HTTPRoute")
        self.assertEqual(route["spec"]["hostnames"], ["vault.thecavespace.net"])
        self.assertEqual(route["spec"]["parentRefs"][0]["sectionName"], "vault")
        self.assertEqual(
            route["spec"]["rules"][0]["backendRefs"], [{"name": "vault", "port": 8200}]
        )
        policy = next(item for item in resources if item["kind"] == "BackendTLSPolicy")
        route_wave = int(
            route["metadata"]
            .get("annotations", {})
            .get("argocd.argoproj.io/sync-wave", "0")
        )
        policy_wave = int(
            policy["metadata"]
            .get("annotations", {})
            .get("argocd.argoproj.io/sync-wave", "0")
        )
        self.assertLessEqual(route_wave, policy_wave)
        self.assertEqual(
            policy["spec"]["targetRefs"],
            [{"group": "", "kind": "Service", "name": "vault", "sectionName": "https"}],
        )
        self.assertEqual(
            policy["spec"]["validation"],
            {
                "hostname": "vault.thecavespace.net",
                "wellKnownCACertificates": "System",
            },
        )
        certificate = next(item for item in resources if item["kind"] == "Certificate")
        self.assertEqual(
            certificate["spec"]["issuerRef"]["name"], "letsencrypt-production"
        )
        self.assertEqual(certificate["spec"]["dnsNames"], ["vault.thecavespace.net"])

    def test_only_private_admin_proxy_can_reach_vault(self):
        policies = self.rendered("system-network-policies.yaml")
        ingress = next(
            item
            for item in policies
            if item["kind"] == "NetworkPolicy"
            and item["metadata"]["namespace"] == "vault"
            and item["metadata"]["name"] == "allow-private-admin"
        )
        peer = ingress["spec"]["ingress"][0]["from"][0]
        self.assertEqual(
            peer["namespaceSelector"]["matchLabels"],
            {"kubernetes.io/metadata.name": "private-admin"},
        )
        proxy = next(
            item
            for item in policies
            if item["kind"] == "CiliumNetworkPolicy"
            and item["metadata"]["namespace"] == "private-admin"
            and item["metadata"]["name"] == "private-proxy"
        )
        self.assertEqual(
            peer["podSelector"]["matchLabels"],
            proxy["spec"]["endpointSelector"]["matchLabels"],
        )
        self.assertEqual(
            ingress["spec"]["ingress"][0]["ports"], [{"protocol": "TCP", "port": 8200}]
        )
        egress = [
            rule
            for rule in proxy["spec"]["egress"]
            if any(
                ep.get("matchLabels", {}).get("k8s:io.kubernetes.pod.namespace")
                == "vault"
                for ep in rule.get("toEndpoints", [])
            )
        ]
        self.assertEqual(
            egress,
            [
                {
                    "toEndpoints": [
                        {
                            "matchLabels": {
                                "k8s:io.kubernetes.pod.namespace": "vault",
                                "k8s:app.kubernetes.io/name": "vault",
                                "k8s:component": "server",
                            }
                        }
                    ],
                    "toPorts": [{"ports": [{"port": "8200", "protocol": "TCP"}]}],
                }
            ],
        )

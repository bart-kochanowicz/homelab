import copy
import ipaddress
import json
import subprocess

from .support import GatewayTestCase


class ArgoCDGatewayTests(GatewayTestCase):
    def test_argocd_preserves_the_reload_hash_without_hiding_other_drift(self):
        resources = self.rendered("system-argocd.yaml")
        appset = next(item for item in resources if item["kind"] == "ApplicationSet")
        spec = appset["spec"]["template"]["spec"]
        self.assertIn(
            "RespectIgnoreDifferences=true", spec["syncPolicy"]["syncOptions"]
        )
        self.assertEqual(len(spec["ignoreDifferences"]), 2)
        self.assertEqual(
            {rule["name"] for rule in spec["ignoreDifferences"]},
            {"home-assistant", "n8n"},
        )
        for rule in spec["ignoreDifferences"]:
            name = rule["name"]
            with self.subTest(application=name):
                self.assertEqual(
                    {
                        key: value
                        for key, value in rule.items()
                        if key != "jqPathExpressions"
                    },
                    {
                        "group": "apps",
                        "kind": "Deployment",
                        "name": name,
                        "namespace": name,
                    },
                )
                deployment = next(
                    item
                    for item in self.rendered(f"apps-{name}.yaml")
                    if item["kind"] == "Deployment"
                )
                drifted = copy.deepcopy(deployment)
                container = drifted["spec"]["template"]["spec"]["containers"][0]
                secret = deployment["metadata"]["annotations"][
                    "secret.reloader.stakater.com/reload"
                ]
                hash_env = "STAKATER_" + secret.replace("-", "_").upper() + "_SECRET"
                container["env"].append({"name": hash_env, "value": "renewed-hash"})

                def normalize(document):
                    result = subprocess.run(
                        ["jq", "del(" + rule["jqPathExpressions"][0] + ")"],
                        input=json.dumps(document),
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    return json.loads(result.stdout)

                self.assertEqual(normalize(drifted), normalize(deployment))
                container["image"] = "unexpected-image"
                container["env"][0]["value"] = "unexpected-timezone"
                self.assertNotEqual(normalize(drifted), normalize(deployment))
                reloader = next(
                    item
                    for item in resources
                    if item["kind"] == "Application"
                    and item["metadata"]["name"] == f"{name}-reloader"
                )
                self.assertNotIn("automated", reloader["spec"]["syncPolicy"])
                self.assertEqual(reloader["spec"]["destination"]["namespace"], name)

    def test_argocd_routes_separate_native_grpc_and_ui_with_verified_backend_tls(self):
        resources = self.rendered("system-argocd.yaml")
        route = next(item for item in resources if item["kind"] == "HTTPRoute")
        service = next(item for item in resources if item["kind"] == "Service")
        policy = next(item for item in resources if item["kind"] == "BackendTLSPolicy")
        self.assertEqual(route["metadata"]["namespace"], "argocd")
        self.assertEqual(
            route["spec"]["parentRefs"],
            [
                {
                    "name": "private-admin",
                    "namespace": "private-admin",
                    "sectionName": "argocd",
                }
            ],
        )
        config = next(
            item
            for item in resources
            if item["kind"] == "ConfigMap" and item["metadata"]["name"] == "argocd-cm"
        )
        hostname = route["spec"]["hostnames"][0]
        self.assertEqual(config["data"]["url"], "https://" + hostname)
        self.assertIn(
            "redirectURI: https://" + hostname + "/api/dex/callback",
            config["data"]["dex.config"],
        )
        grpc, ui = route["spec"]["rules"]
        self.assertEqual(
            grpc["matches"],
            [
                {
                    "headers": [
                        {
                            "name": "Content-Type",
                            "type": "Exact",
                            "value": content_type,
                        }
                    ]
                }
                for content_type in ("application/grpc", "application/grpc+proto")
            ],
        )
        self.assertEqual(
            grpc["backendRefs"], [{"name": service["metadata"]["name"], "port": 443}]
        )
        self.assertEqual(
            ui["matches"], [{"path": {"type": "PathPrefix", "value": "/"}}]
        )
        self.assertEqual(ui["backendRefs"], [{"name": "argocd-server", "port": 443}])
        for rule in (grpc, ui):
            self.assertEqual(rule["timeouts"], {"request": "0s"})
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertEqual(
            service["spec"]["ports"],
            [
                {
                    "name": "https",
                    "port": 443,
                    "targetPort": 8080,
                    "protocol": "TCP",
                    "appProtocol": "kubernetes.io/h2c",
                }
            ],
        )
        self.assertEqual(
            policy["spec"]["targetRefs"],
            [
                {
                    "group": "",
                    "kind": "Service",
                    "name": name,
                    "sectionName": "https",
                }
                for name in ("argocd-server", service["metadata"]["name"])
            ],
        )
        validation = policy["spec"]["validation"]
        certificate = next(
            item
            for item in self.rendered("system-cert-manager-ca.yaml")
            if item["kind"] == "Certificate"
            and item["metadata"]["namespace"] == "argocd"
        )
        self.assertEqual(
            validation, {"hostname": hostname, "wellKnownCACertificates": "System"}
        )
        self.assertEqual(certificate["spec"]["dnsNames"], [hostname])
        self.assertEqual(certificate["spec"]["secretName"], "argocd-server-tls")
        self.assertEqual(
            certificate["spec"]["issuerRef"],
            {
                "name": "letsencrypt-production",
                "kind": "ClusterIssuer",
                "group": "cert-manager.io",
            },
        )
        self.assertEqual(certificate["spec"]["privateKey"]["rotationPolicy"], "Always")
        self.assertFalse(
            any(
                item["kind"] == "ConfigMap" and "ca.crt" in item.get("data", {})
                for item in resources
            )
        )
        server_policy = next(
            item
            for item in self.rendered("system-network-policies.yaml")
            if item["kind"] == "NetworkPolicy"
            and item["metadata"]["name"] == "allow-argocd-server"
        )
        self.assertEqual(
            service["spec"]["selector"],
            server_policy["spec"]["podSelector"]["matchLabels"],
        )

    def test_argocd_access_is_limited_to_admin_proxy_release_and_management(self):
        policies = self.rendered("system-network-policies.yaml")
        server = next(
            item
            for item in policies
            if item["kind"] == "NetworkPolicy"
            and item["metadata"]["namespace"] == "argocd"
        )
        self.assertEqual(
            server["spec"]["podSelector"],
            {
                "matchLabels": {
                    "app.kubernetes.io/instance": "argocd",
                    "app.kubernetes.io/name": "argocd-server",
                }
            },
        )
        self.assertEqual(server["spec"]["policyTypes"], ["Ingress"])
        self.assertNotIn("egress", server["spec"])
        admin = next(
            item
            for item in policies
            if item["kind"] == "CiliumNetworkPolicy"
            and item["metadata"]["name"] == "private-proxy"
            and item["metadata"]["namespace"] == "private-admin"
        )
        backend = [
            rule
            for rule in admin["spec"]["egress"]
            if any(
                port["port"] == "8080"
                for block in rule["toPorts"]
                for port in block["ports"]
            )
        ]
        self.assertEqual(
            backend,
            [
                {
                    "toEndpoints": [
                        {
                            "matchLabels": {
                                "k8s:io.kubernetes.pod.namespace": "argocd",
                                "k8s:app.kubernetes.io/instance": "argocd",
                                "k8s:app.kubernetes.io/name": "argocd-server",
                            }
                        }
                    ],
                    "toPorts": [{"ports": [{"port": "8080", "protocol": "TCP"}]}],
                }
            ],
        )

        def allows(
            namespace: str, labels: dict[str, str], address: str, port: int
        ) -> bool:
            for rule in server["spec"]["ingress"]:
                if {"port": port, "protocol": "TCP"} not in rule["ports"]:
                    continue
                for peer in rule["from"]:
                    if "ipBlock" in peer:
                        if ipaddress.ip_address(address) in ipaddress.ip_network(
                            peer["ipBlock"]["cidr"]
                        ):
                            return True
                    else:
                        expected_namespace = (
                            peer.get("namespaceSelector", {})
                            .get("matchLabels", {})
                            .get("kubernetes.io/metadata.name", "argocd")
                        )
                        expected_labels = peer.get("podSelector", {}).get(
                            "matchLabels", {}
                        )
                        if (
                            namespace == expected_namespace
                            and expected_labels.items() <= labels.items()
                        ):
                            return True
            return False

        proxy_labels = admin["spec"]["endpointSelector"]["matchLabels"]
        release_labels = {"app.kubernetes.io/instance": "argocd"}
        cases = [
            ("private-admin", proxy_labels, "10.244.1.10", 8080, True),
            ("private-home", proxy_labels, "10.244.1.10", 8080, False),
            ("private-admin", {}, "10.244.1.10", 8080, False),
            ("n8n", release_labels, "10.244.1.10", 8080, False),
            ("argocd", release_labels, "10.244.1.10", 8080, True),
            ("argocd", {}, "10.244.1.10", 8080, False),
            (None, {}, "10.0.80.42", 8080, True),
            (None, {}, "10.0.100.42", 8080, True),
            (None, {}, "10.0.40.42", 8080, False),
            (
                "monitoring",
                {"app.kubernetes.io/name": "prometheus"},
                "10.244.1.10",
                8083,
                True,
            ),
            (
                "monitoring",
                {"app.kubernetes.io/name": "prometheus"},
                "10.244.1.10",
                8080,
                False,
            ),
            ("private-admin", proxy_labels, "10.244.1.10", 8083, False),
            (None, {}, "10.0.80.42", 8083, False),
        ]
        for namespace, labels, address, port, expected in cases:
            with self.subTest(
                namespace=namespace, labels=labels, address=address, port=port
            ):
                self.assertEqual(allows(namespace, labels, address, port), expected)

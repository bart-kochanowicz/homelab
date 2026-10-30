from typing import Any

from .support import GatewayTestCase


class GatewayListenerTests(GatewayTestCase):
    def test_listener_attachment_is_limited_to_its_application(self):
        expected = {
            "ha.thecavespace.net": ("private-home", "home-assistant"),
            "crafty-controller.thecavespace.net": (
                "private-admin",
                "crafty-controller",
            ),
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
                secret = (
                    f"{namespace}-argocd-tls"
                    if listener["name"] == "argocd"
                    else f"{namespace}-tls"
                )
                self.assertEqual(
                    listener["tls"]["certificateRefs"],
                    [
                        {"group": "", "kind": "Secret", "name": secret},
                    ],
                )
                namespaces = listener["allowedRoutes"]["namespaces"]
                self.assertEqual(namespaces["from"], "Selector")
                labels = namespaces["selector"]["matchLabels"]
                self.assertEqual(set(labels), {"kubernetes.io/metadata.name"})
                observed[listener["hostname"]] = (
                    namespace,
                    labels["kubernetes.io/metadata.name"],
                )
        self.assertEqual(observed, expected)
        self.assertFalse(self.resources_of_kind("ReferenceGrant"))
        self.assertFalse(self.resources_of_kind("HTTPRoute"))

    def test_proxies_do_not_trust_client_supplied_forwarding_headers(self):
        policies = self.resources_of_kind("ClientTrafficPolicy")
        self.assertEqual(len(policies), 3)
        for policy in policies:
            namespace = policy["metadata"]["namespace"]
            target = {
                "group": "gateway.networking.k8s.io",
                "kind": "Gateway",
                "name": namespace,
            }
            if policy["metadata"]["name"] == "private-admin-argocd":
                target["sectionName"] = "argocd"
            self.assertEqual(
                policy["spec"]["targetRefs"],
                [
                    target,
                ],
            )
            detection = policy["spec"]["clientIPDetection"]
            self.assertEqual(detection, {"directSourceIP": {}})
            expected_alpn = (
                ["http/1.1"]
                if policy["metadata"]["name"] == "private-admin"
                else ["h2", "http/1.1"]
            )
            self.assertEqual(policy["spec"]["tls"]["alpnProtocols"], expected_alpn)

    def test_http2_cannot_coalesce_between_separate_admin_listeners(self):
        certificates = {
            (item["metadata"]["namespace"], item["spec"]["secretName"]): item
            for item in self.rendered("system-cert-manager-acme.yaml")
            if item["kind"] == "Certificate"
        }
        policies: dict[tuple[str, str, str | None], dict[str, Any]] = {}
        for policy in self.resources_of_kind("ClientTrafficPolicy"):
            for target in policy["spec"]["targetRefs"]:
                policies[
                    (
                        policy["metadata"]["namespace"],
                        target["name"],
                        target.get("sectionName"),
                    )
                ] = policy
        for gateway in self.resources_of_kind("Gateway"):
            namespace, name = (
                gateway["metadata"]["namespace"],
                gateway["metadata"]["name"],
            )
            if len(gateway["spec"]["listeners"]) == 1:
                continue
            default = policies[(namespace, name, None)]
            for listener in gateway["spec"]["listeners"]:
                policy = policies.get((namespace, name, listener["name"]), default)
                if "h2" not in policy["spec"]["tls"]["alpnProtocols"]:
                    continue
                with self.subTest(listener=listener["name"]):
                    for ref in listener["tls"]["certificateRefs"]:
                        certificate = certificates[
                            (ref.get("namespace", namespace), ref["name"])
                        ]
                        self.assertEqual(
                            certificate["spec"]["dnsNames"],
                            [listener["hostname"]],
                            "HTTP/2 listeners must not present certificates covering other admin origins",
                        )
                        self.assertEqual(
                            certificate["spec"]["issuerRef"]["name"],
                            "letsencrypt-production",
                        )

    def test_proxy_images_and_runtime_do_not_require_host_privileges(self):
        for proxy in self.resources_of_kind("EnvoyProxy"):
            provider = proxy["spec"]["provider"]["kubernetes"]
            deployment = provider["envoyDeployment"]
            container = deployment["container"]
            self.assertRegex(
                container["image"], r":distroless-v1\.39\.3@sha256:[0-9a-f]{64}$"
            )
            self.assertEqual(
                container["securityContext"]["capabilities"]["drop"], ["ALL"]
            )
            self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
            self.assertTrue(deployment["pod"]["securityContext"]["runAsNonRoot"])
            self.assertGreaterEqual(deployment["replicas"], 2)
            self.assertFalse(proxy["spec"]["mergeGateways"])
            self.assertFalse(
                any(
                    "patch" in value
                    for value in provider.values()
                    if isinstance(value, dict)
                )
            )

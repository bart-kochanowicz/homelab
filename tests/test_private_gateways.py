import copy
import ipaddress
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / ".cache/metallb-schemas"
ENVOY_SCHEMAS = ROOT / ".cache/envoy-gateway-schemas"


class PrivateGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SCHEMAS.is_dir() or not ENVOY_SCHEMAS.is_dir():
            raise RuntimeError("Run make validate-metallb validate-envoy-gateway before these tests")
        result = subprocess.run(
            ["yq", "-o=json", "-I=0", "select(. != null)", str(ROOT / ".cache/rendered/system-gateways.yaml")],
            check=True, capture_output=True, text=True, timeout=15,
        )
        cls.resources = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        cls.resources += cls.rendered("system-metallb-config.yaml")

    def resources_of_kind(self, kind):
        return [item for item in self.resources if item["kind"] == kind]

    def validate(self, document):
        with tempfile.TemporaryDirectory(prefix="gateway-schema-", dir=ROOT / ".cache") as directory:
            fixture = Path(directory) / "resource.json"
            fixture.write_text(json.dumps(document))
            return subprocess.run(
                ["kubeconform", "-strict", "-summary", "-schema-location",
                 str((ENVOY_SCHEMAS if document["apiVersion"].startswith("gateway.envoyproxy.io/") else SCHEMAS)
                     / "{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"), str(fixture)],
                capture_output=True, text=True, timeout=15,
            )

    def test_schemas_reject_invalid_admission_configuration(self):
        config = self.resources_of_kind("EnvoyProxy")[0]
        pool = self.resources_of_kind("IPAddressPool")[0]
        announcement = self.resources_of_kind("L2Advertisement")[0]
        for resource in (config, pool, announcement, self.resources_of_kind("ClientTrafficPolicy")[0]):
            with self.subTest(kind=resource["kind"], valid=True):
                result = self.validate(resource)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Valid: 1, Invalid: 0, Errors: 0, Skipped: 0", result.stdout)
        invalid_examples = []
        invalid = copy.deepcopy(config)
        invalid["spec"]["provider"]["kubernetes"]["envoyService"]["sourceRanges"] = ["0.0.0.0/0"]
        invalid_examples.append(invalid)
        invalid = copy.deepcopy(config)
        invalid["spec"]["provider"]["kubernetes"]["envoyService"]["allocateLoadBalancerNodePorts"] = "false"
        invalid_examples.append(invalid)
        invalid = copy.deepcopy(pool)
        invalid["spec"]["serviceAllocation"]["serviceSelectors"] = "private-home"
        invalid_examples.append(invalid)
        invalid = copy.deepcopy(announcement)
        invalid["spec"]["interfaces"] = "eno1"
        invalid_examples.append(invalid)
        for invalid in invalid_examples:
            with self.subTest(kind=invalid["kind"], spec=invalid["spec"]):
                result = self.validate(invalid)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Invalid: 1", result.stdout)

    def test_client_admission_excludes_other_lans_nodes_and_pods(self):
        classes = {item["metadata"]["name"]: item for item in self.resources_of_kind("GatewayClass")}
        allowed = {
            "private-home": {"10.0.40.42", "10.0.80.42", "10.0.100.42"},
            "private-admin": {"10.0.80.42", "10.0.100.42"},
        }
        clients = {"10.0.30.42", "10.0.40.42", "10.0.50.42", "10.0.60.42",
                   "10.0.70.11", "10.0.70.42", "10.0.80.42", "10.0.90.42",
                   "10.0.100.42", "10.244.1.42", "192.0.2.42"}
        for config in self.resources_of_kind("EnvoyProxy"):
            name = config["metadata"]["name"]
            service = config["spec"]["provider"]["kubernetes"]["envoyService"]
            ranges = [ipaddress.ip_network(cidr) for cidr in service["loadBalancerSourceRanges"]]
            admitted = {client for client in clients if any(ipaddress.ip_address(client) in net for net in ranges)}
            self.assertEqual(admitted, allowed[name])
            self.assertFalse(service["allocateLoadBalancerNodePorts"])
            self.assertEqual(service["externalTrafficPolicy"], "Local")
            self.assertEqual(config["spec"]["ipFamily"], "IPv4")
        for gateway in self.resources_of_kind("Gateway"):
            namespace = gateway["metadata"]["namespace"]
            parameters = classes[gateway["spec"]["gatewayClassName"]]["spec"]["parametersRef"]
            self.assertEqual(parameters["kind"], "EnvoyProxy")
            self.assertEqual(parameters["group"], "gateway.envoyproxy.io")
            self.assertEqual(classes[gateway["spec"]["gatewayClassName"]]["spec"]["controllerName"],
                             "gateway.envoyproxy.io/gatewayclass-controller")
            self.assertEqual((parameters["namespace"], parameters["name"]), (namespace, namespace))

    def test_ip_allocation_and_announcements_require_exact_service_identity(self):
        pools = self.resources_of_kind("IPAddressPool")
        proxies = {item["metadata"]["name"]: item for item in self.resources_of_kind("EnvoyProxy")}
        self.assertEqual(len(pools), 2)
        addresses = set()
        for pool in pools:
            name = pool["metadata"]["name"]
            self.assertEqual(pool["metadata"]["namespace"], "metallb-system")
            self.assertFalse(pool["spec"]["autoAssign"])
            allocation = pool["spec"]["serviceAllocation"]
            self.assertEqual(allocation["namespaces"], [name])
            self.assertEqual(allocation["serviceSelectors"], [{"matchLabels": {
                "app.kubernetes.io/managed-by": "envoy-gateway",
                "app.kubernetes.io/component": "proxy",
                "gateway.envoyproxy.io/owning-gateway-name": name,
                "gateway.envoyproxy.io/owning-gateway-namespace": name,
            }}])
            network = ipaddress.ip_network(pool["spec"]["addresses"][0])
            self.assertEqual(network.prefixlen, 32)
            addresses.add(str(network.network_address))
            service = proxies[name]["spec"]["provider"]["kubernetes"]["envoyService"]
            self.assertEqual(service["loadBalancerClass"], "metallb.io/metallb")
            self.assertEqual(service["annotations"], {
                "metallb.io/address-pool": name,
                "metallb.io/loadBalancerIPs": str(network.network_address),
            })
            self.assertEqual(service["name"], "envoy-" + name)
        self.assertEqual(addresses, {"10.0.70.200", "10.0.70.201"})
        advertisements = self.resources_of_kind("L2Advertisement")
        self.assertEqual(len(advertisements), 1)
        self.assertEqual(advertisements[0]["spec"], {
            "ipAddressPools": ["private-home", "private-admin"],
            "nodeSelectors": [
                {"matchLabels": {"kubernetes.io/hostname": "talos-2jn-7he"}},
                {"matchLabels": {"kubernetes.io/hostname": "talos-p5e-e9e"}},
            ],
            "interfaces": ["eno1"],
        })

    def test_listener_attachment_is_limited_to_its_application(self):
        expected = {
            "ha.thecavespace.net": ("private-home", "home-assistant"),
            "crafty-controller.thecavespace.net": ("private-admin", "crafty-controller"),
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
                self.assertEqual(listener["tls"]["certificateRefs"], [
                    {"group": "", "kind": "Secret", "name": f"{namespace}-tls"},
                ])
                namespaces = listener["allowedRoutes"]["namespaces"]
                self.assertEqual(namespaces["from"], "Selector")
                labels = namespaces["selector"]["matchLabels"]
                self.assertEqual(set(labels), {"kubernetes.io/metadata.name"})
                observed[listener["hostname"]] = (namespace, labels["kubernetes.io/metadata.name"])
        self.assertEqual(observed, expected)
        self.assertFalse(self.resources_of_kind("ReferenceGrant"))
        self.assertFalse(self.resources_of_kind("HTTPRoute"))

    def test_proxies_do_not_trust_client_supplied_forwarding_headers(self):
        policies = self.resources_of_kind("ClientTrafficPolicy")
        self.assertEqual(len(policies), 2)
        for policy in policies:
            namespace = policy["metadata"]["namespace"]
            self.assertEqual(policy["spec"]["targetRefs"], [
                {"group": "gateway.networking.k8s.io", "kind": "Gateway", "name": namespace},
            ])
            detection = policy["spec"]["clientIPDetection"]
            self.assertEqual(detection, {"xForwardedFor": {"numTrustedHops": 0}})
            self.assertEqual(policy["spec"]["tls"]["alpnProtocols"], ["h2", "http/1.1"])

    def test_home_assistant_route_only_uses_its_private_home_listener_and_service(self):
        resources = self.rendered("apps-home-assistant.yaml")
        routes = [item for item in resources if item["kind"] == "HTTPRoute"]
        self.assertEqual(len(routes), 1)
        route = routes[0]
        self.assertEqual(route["metadata"]["namespace"], "home-assistant")
        spec = route["spec"]
        self.assertEqual(spec["parentRefs"], [{
            "name": "private-home", "namespace": "private-home", "sectionName": "home-assistant",
        }])
        self.assertEqual(spec["hostnames"], ["ha.thecavespace.net"])
        self.assertEqual(len(spec["rules"]), 1)
        rule = spec["rules"][0]
        self.assertEqual(set(rule), {"matches", "backendRefs", "timeouts"})
        self.assertEqual(rule["matches"], [{"path": {"type": "PathPrefix", "value": "/"}}])
        self.assertEqual(rule["backendRefs"], [{"name": "home-assistant", "port": 8123}])
        self.assertEqual(rule["timeouts"], {"request": "0s"})
        service = next(item for item in resources if item["kind"] == "Service" and
                       item["metadata"]["name"] == rule["backendRefs"][0]["name"])
        self.assertEqual(service["metadata"]["namespace"], route["metadata"]["namespace"])
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertIn({"name": "http", "port": 8123, "targetPort": 8123, "protocol": "TCP"},
                      service["spec"]["ports"])

    def test_crafty_admin_route_requires_verified_tls_on_the_panel_port(self):
        resources = self.rendered("apps-crafty-controller.yaml")
        route = next(item for item in resources if item["kind"] == "HTTPRoute")
        namespace = route["metadata"]["namespace"]
        self.assertEqual(namespace, "crafty-controller")
        self.assertEqual(route["spec"]["parentRefs"], [{
            "name": "private-admin", "namespace": "private-admin", "sectionName": "crafty-controller",
        }])
        self.assertEqual(route["spec"]["hostnames"], ["crafty-controller.thecavespace.net"])
        self.assertEqual(len(route["spec"]["rules"]), 1)
        rule = route["spec"]["rules"][0]
        self.assertEqual(rule, {
            "matches": [{"path": {"type": "PathPrefix", "value": "/"}}],
            "backendRefs": [{"name": "crafty-controller", "port": 8443}],
            "timeouts": {"request": "0s"},
        })
        service = next(item for item in resources if item["kind"] == "Service" and
                       item["metadata"]["name"] == rule["backendRefs"][0]["name"])
        port = next(item for item in service["spec"]["ports"] if
                    item["port"] == rule["backendRefs"][0]["port"])
        policy = next(item for item in resources if item["kind"] == "BackendTLSPolicy")
        self.assertEqual(policy["metadata"]["namespace"], namespace)
        self.assertEqual(service["metadata"]["namespace"], namespace)
        self.assertEqual(policy["spec"]["targetRefs"], [{
            "group": "", "kind": "Service", "name": service["metadata"]["name"],
            "sectionName": port["name"],
        }])
        certificate = next(item for item in resources if item["kind"] == "Certificate")
        validation = policy["spec"]["validation"]
        self.assertEqual(validation, {
            "hostname": route["spec"]["hostnames"][0], "wellKnownCACertificates": "System",
        })
        self.assertEqual(certificate["spec"]["dnsNames"], [validation["hostname"]])
        self.assertLess(int(certificate["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]),
                        int(policy["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]))
        self.assertLess(int(policy["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]),
                        int(route["metadata"].get("annotations", {}).get("argocd.argoproj.io/sync-wave", 0)))

    def test_crafty_certificate_projection_can_receive_renewed_key_pairs(self):
        resources = self.rendered("apps-crafty-controller.yaml")
        certificate = next(item for item in resources if item["kind"] == "Certificate")
        self.assertEqual(certificate["spec"]["issuerRef"], {
            "name": "letsencrypt-production", "kind": "ClusterIssuer", "group": "cert-manager.io",
        })
        self.assertEqual(certificate["spec"]["privateKey"]["rotationPolicy"], "Always")
        deployment = next(item for item in resources if item["kind"] == "Deployment")
        pod = deployment["spec"]["template"]["spec"]
        mount = next(item for item in pod["containers"][0]["volumeMounts"] if
                     item["mountPath"] == "/crafty/app/config/web/certs")
        self.assertTrue(mount["readOnly"])
        self.assertFalse({"subPath", "subPathExpr"} & set(mount))
        volume = next(item for item in pod["volumes"] if item["name"] == mount["name"])
        self.assertEqual(volume["secret"], {
            "secretName": certificate["spec"]["secretName"],
            "defaultMode": 0o440,
            "items": [
                {"key": "tls.crt", "path": "commander.cert.pem"},
                {"key": "tls.key", "path": "commander.key.pem"},
            ],
        })

    def test_proxy_images_and_runtime_do_not_require_host_privileges(self):
        for proxy in self.resources_of_kind("EnvoyProxy"):
            provider = proxy["spec"]["provider"]["kubernetes"]
            deployment = provider["envoyDeployment"]
            container = deployment["container"]
            self.assertRegex(container["image"], r":distroless-v1\.39\.3@sha256:[0-9a-f]{64}$")
            self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
            self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
            self.assertTrue(deployment["pod"]["securityContext"]["runAsNonRoot"])
            self.assertGreaterEqual(deployment["replicas"], 2)
            self.assertFalse(proxy["spec"]["mergeGateways"])
            self.assertFalse(any("patch" in value for value in provider.values() if isinstance(value, dict)))

    @staticmethod
    def rendered(name):
        result = subprocess.run(
            ["yq", "-o=json", "-I=0", "select(. != null)", str(ROOT / ".cache/rendered" / name)],
            check=True, capture_output=True, text=True, timeout=15,
        )
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def test_controller_crds_have_one_owner(self):
        controller = self.rendered("helm-envoy-gateway.yaml")
        extensions = self.rendered("helm-envoy-gateway-crds.yaml")
        standard = self.rendered("system-gateway-api-crds.yaml")
        self.assertFalse(any(item["kind"] == "CustomResourceDefinition" for item in controller))
        self.assertGreaterEqual(len(extensions), 2)
        self.assertTrue(all(item["kind"] == "CustomResourceDefinition" and
                            item["spec"]["group"] == "gateway.envoyproxy.io" for item in extensions))
        self.assertTrue(all(item["spec"]["group"] == "gateway.networking.k8s.io" for item in standard))
        self.assertFalse({item["metadata"]["name"] for item in extensions} &
                         {item["metadata"]["name"] for item in standard})

        argocd = self.rendered("system-argocd.yaml")
        apps = [item for item in argocd if item["kind"] == "Application" and
                item["metadata"]["name"] in {"envoy-gateway", "envoy-gateway-crds", "gateways"}]
        self.assertEqual(len(apps), 3)
        for app in apps:
            self.assertNotIn("automated", app["spec"]["syncPolicy"])
            self.assertNotIn("finalizers", app["metadata"])
            self.assertIn("FailOnSharedResource=true", app["spec"]["syncPolicy"]["syncOptions"])
        applications = next(item for item in argocd if item["kind"] == "AppProject" and
                            item["metadata"]["name"] == "applications")
        self.assertFalse(any(item["group"] == "gateway.envoyproxy.io" for item in
                             applications["spec"]["namespaceResourceWhitelist"]))

    def test_controller_can_watch_its_own_endpoints_without_cluster_wide_access(self):
        resources = self.rendered("helm-envoy-gateway.yaml")
        config = next(item for item in resources if item["kind"] == "ConfigMap" and
                      item["metadata"]["name"] == "envoy-gateway-config")
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as directory:
            fixture = Path(directory) / "envoy-gateway.yaml"
            fixture.write_text(config["data"]["envoy-gateway.yaml"])
            result = subprocess.run(["yq", "-o=json", ".provider.kubernetes.watch", str(fixture)],
                                    check=True, capture_output=True, text=True, timeout=15)
        watch = json.loads(result.stdout)
        self.assertEqual(watch["type"], "Namespaces")
        self.assertIn("envoy-gateway-system", watch["namespaces"])
        account = {"kind": "ServiceAccount", "name": "envoy-gateway",
                   "namespace": "envoy-gateway-system"}
        roles = {(item["kind"], item["metadata"].get("namespace"), item["metadata"]["name"]): item
                 for item in resources if item["kind"] in {"Role", "ClusterRole"}}
        granted = set()
        for binding in resources:
            if binding["kind"] not in {"RoleBinding", "ClusterRoleBinding"}:
                continue
            if account not in binding.get("subjects", []):
                continue
            ref = binding["roleRef"]
            namespace = binding["metadata"].get("namespace")
            role = roles[(ref["kind"], namespace if ref["kind"] == "Role" else None, ref["name"])]
            for rule in role["rules"]:
                if "discovery.k8s.io" in rule["apiGroups"] and "endpointslices" in rule["resources"]:
                    self.assertEqual(binding["kind"], "RoleBinding")
                    self.assertEqual(set(rule["verbs"]), {"get", "list", "watch"})
                    if namespace == account["namespace"]:
                        granted.update(rule["verbs"])
        self.assertEqual(granted, {"get", "list", "watch"})

    def test_proxies_deny_application_pods_and_limit_backend_access(self):
        policies = self.rendered("system-network-policies.yaml")
        proxies = [item for item in policies if item["kind"] == "CiliumNetworkPolicy" and
                   item["metadata"]["name"] == "private-proxy"]
        self.assertEqual({item["metadata"]["namespace"] for item in proxies},
                         {"private-home", "private-admin"})
        for policy in proxies:
            self.assertEqual(policy["spec"]["ingressDeny"][0]["fromEndpoints"], [
                {"matchExpressions": [{"key": "k8s:io.kubernetes.pod.namespace", "operator": "Exists"}]},
            ])
            ports = {port["port"] for rule in policy["spec"]["egress"]
                     for to_port in rule["toPorts"] for port in to_port["ports"]}
            expected_ports = {"53", "18000"}
            if policy["metadata"]["namespace"] == "private-home":
                expected_ports.add("8123")
            else:
                expected_ports.add("8443")
            self.assertEqual(ports, expected_ports)
            self.assertEqual(set(policy["spec"]["ingress"][0]), {"fromCIDR", "toPorts"})
            self.assertEqual(len(policy["spec"]["ingress"]), 1)

    def test_crafty_panel_access_requires_admin_proxy_and_exact_backend(self):
        policies = self.rendered("system-network-policies.yaml")
        crafty = next(item for item in policies if item["kind"] == "NetworkPolicy" and
                      item["metadata"]["namespace"] == "crafty-controller" and
                      item["metadata"]["name"] == "allow-crafty")
        self.assertEqual(crafty["spec"]["podSelector"], {
            "matchLabels": {"app.kubernetes.io/name": "crafty-controller"},
        })
        proxy_ingress = [rule for rule in crafty["spec"]["ingress"] if any(
            "namespaceSelector" in peer or "podSelector" in peer for peer in rule["from"]
        )]
        self.assertEqual(proxy_ingress, [{
            "from": [{
                "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "private-admin"}},
                "podSelector": {"matchLabels": {
                    "app.kubernetes.io/managed-by": "envoy-gateway",
                    "app.kubernetes.io/component": "proxy",
                    "gateway.envoyproxy.io/owning-gateway-name": "private-admin",
                }},
            }],
            "ports": [{"protocol": "TCP", "port": 8443}],
        }])
        admin = next(item for item in policies if item["kind"] == "CiliumNetworkPolicy" and
                     item["metadata"]["name"] == "private-proxy" and
                     item["metadata"]["namespace"] == "private-admin")
        self.assertEqual(admin["spec"]["endpointSelector"], {
            "matchLabels": proxy_ingress[0]["from"][0]["podSelector"]["matchLabels"],
        })
        backend_rules = [rule for rule in admin["spec"]["egress"] if any(
            port["port"] not in {"53", "18000"}
            for block in rule["toPorts"] for port in block["ports"]
        )]
        self.assertEqual(backend_rules, [{
            "toEndpoints": [{"matchLabels": {
                "k8s:io.kubernetes.pod.namespace": "crafty-controller",
                "k8s:app.kubernetes.io/name": "crafty-controller",
            }}],
            "toPorts": [{"ports": [{"port": "8443", "protocol": "TCP"}]}],
        }])

    def test_home_assistant_host_access_requires_home_proxy_identity(self):
        policies = self.rendered("system-network-policies.yaml")
        host = next(item for item in policies if item["kind"] == "CiliumClusterwideNetworkPolicy" and
                    item["metadata"]["name"] == "homelab-host-firewall")
        proxy_rules = [rule for rule in host["spec"]["ingress"] if any(
            selector.get("matchLabels", {}).get("k8s:io.kubernetes.pod.namespace") == "private-home"
            for selector in rule.get("fromEndpoints", [])
        )]
        self.assertEqual(len(proxy_rules), 1)
        rule = proxy_rules[0]
        self.assertEqual(set(rule), {"fromEndpoints", "toPorts"})
        self.assertEqual(rule["fromEndpoints"], [{"matchLabels": {
            "k8s:io.kubernetes.pod.namespace": "private-home",
            "k8s:app.kubernetes.io/managed-by": "envoy-gateway",
            "k8s:app.kubernetes.io/component": "proxy",
            "k8s:gateway.envoyproxy.io/owning-gateway-name": "private-home",
        }}])
        ports = [{"ports": [{"port": "8123", "protocol": "TCP"}]}]
        self.assertEqual(rule["toPorts"], ports)
        home = next(item for item in policies if item["kind"] == "CiliumNetworkPolicy" and
                    item["metadata"]["name"] == "private-proxy" and
                    item["metadata"]["namespace"] == "private-home")
        self.assertEqual(home["spec"]["endpointSelector"], {"matchLabels": {
            "app.kubernetes.io/managed-by": "envoy-gateway",
            "app.kubernetes.io/component": "proxy",
            "gateway.envoyproxy.io/owning-gateway-name": "private-home",
        }})
        node_rules = [rule for rule in home["spec"]["egress"] if "toEntities" in rule]
        self.assertEqual(node_rules, [{"toEntities": ["host", "remote-node"], "toPorts": ports}])

    def test_metallb_only_runs_l2_with_a_dedicated_service_class(self):
        resources = self.rendered("helm-metallb.yaml")
        workloads = [item for item in resources if item["kind"] in {"Deployment", "DaemonSet"}]
        self.assertEqual({item["metadata"]["name"] for item in workloads},
                         {"metallb-controller", "metallb-speaker"})
        for workload in workloads:
            pod = workload["spec"]["template"]["spec"]
            self.assertFalse(pod.get("initContainers"))
            self.assertEqual(len(pod["containers"]), 1)
            container = pod["containers"][0]
            self.assertIn("--lb-class=metallb.io/metallb", container["args"])
            self.assertRegex(container["image"], r":v0\.16\.1@sha256:[0-9a-f]{64}$")
            self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
            self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
            secret_envs = {env["name"]: env.get("value") for env in container.get("env", [])
                           if "SECRET" in env["name"]}
            if workload["kind"] == "DaemonSet":
                self.assertTrue(pod["hostNetwork"])
                self.assertIn("--ignore-exclude-lb", container["args"])
                self.assertEqual(container["securityContext"]["capabilities"]["add"], ["NET_RAW"])
                self.assertEqual(secret_envs, {"METALLB_ML_SECRET_KEY_PATH": "/etc/ml_secret_key"})
                self.assertIn({"name": "memberlist", "secret": {
                    "secretName": "metallb-memberlist", "defaultMode": 420,
                }}, pod["volumes"])
            else:
                self.assertEqual(secret_envs, {"METALLB_ML_SECRET_NAME": "metallb-memberlist"})

    def test_metallb_crds_and_configuration_have_separate_manual_owners(self):
        controller = self.rendered("helm-metallb.yaml")
        definitions = self.rendered("system-metallb-crds.yaml")
        self.assertFalse(any(item["kind"] == "CustomResourceDefinition" for item in controller))
        self.assertEqual(len(definitions), 9)
        for item in definitions:
            self.assertEqual(item["kind"], "CustomResourceDefinition")
            self.assertEqual(item["spec"]["group"], "metallb.io")
            self.assertEqual(item["metadata"]["annotations"]["argocd.argoproj.io/sync-options"],
                             "Prune=false,Delete=false")
        argocd = self.rendered("system-argocd.yaml")
        apps = [item for item in argocd if item["kind"] == "Application" and
                item["metadata"]["name"] in {"metallb", "metallb-crds", "metallb-config"}]
        self.assertEqual(len(apps), 3)
        for app in apps:
            self.assertNotIn("automated", app["spec"]["syncPolicy"])
            self.assertNotIn("finalizers", app["metadata"])
            self.assertIn("FailOnSharedResource=true", app["spec"]["syncPolicy"]["syncOptions"])
        applications = next(item for item in argocd if item["kind"] == "AppProject" and
                            item["metadata"]["name"] == "applications")
        self.assertFalse(any(item["group"] == "metallb.io" for item in
                             applications["spec"]["namespaceResourceWhitelist"]))

    def test_metallb_upstream_wildcard_verbs_are_limited_to_status_resources(self):
        for item in self.rendered("helm-metallb.yaml"):
            if item["kind"] not in {"Role", "ClusterRole"}:
                continue
            for rule in item["rules"]:
                self.assertNotIn("*", rule["apiGroups"])
                self.assertNotIn("*", rule["resources"])
                if "*" in rule["verbs"]:
                    self.assertEqual(rule["apiGroups"], ["metallb.io"])
                    self.assertLessEqual(set(rule["resources"]), {
                        "servicel2statuses", "servicel2statuses/status",
                        "servicebgpstatuses", "servicebgpstatuses/status",
                        "configurationstates", "configurationstates/status",
                    })

    def test_cilium_keeps_the_existing_dataplane_and_host_firewall(self):
        config = next(item for item in self.rendered("helm-cilium.yaml") if
                      item["kind"] == "ConfigMap" and item["metadata"]["name"] == "cilium-config")
        data = config["data"]
        for key in ("kube-proxy-replacement", "enable-host-firewall", "enable-host-legacy-routing",
                    "bpf-lb-sock-hostns-only", "bpf-lb-source-range-all-types"):
            self.assertEqual(data[key], "true", key)
        self.assertEqual(data.get("enable-gateway-api", "false"), "false")
        self.assertEqual(data["routing-mode"], "tunnel")
        self.assertEqual(data.get("enable-l2-announcements", "false"), "false")
        self.assertEqual(data["default-lb-service-ipam"], "none")
        self.assertFalse(any(item["kind"] in {"CiliumLoadBalancerIPPool", "CiliumL2AnnouncementPolicy"}
                             for item in self.resources))


if __name__ == "__main__":
    unittest.main()

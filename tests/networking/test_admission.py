import copy
import ipaddress
from typing import Any

from .support import GatewayTestCase


class GatewayAdmissionTests(GatewayTestCase):
    def test_schemas_reject_invalid_admission_configuration(self):
        config = self.resources_of_kind("EnvoyProxy")[0]
        pool = self.resources_of_kind("IPAddressPool")[0]
        announcement = self.resources_of_kind("L2Advertisement")[0]
        for resource in (
            config,
            pool,
            announcement,
            self.resources_of_kind("ClientTrafficPolicy")[0],
        ):
            with self.subTest(kind=resource["kind"], valid=True):
                result = self.validate(resource)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(
                    "Valid: 1, Invalid: 0, Errors: 0, Skipped: 0", result.stdout
                )
        invalid_examples: list[dict[str, Any]] = []
        invalid = copy.deepcopy(config)
        invalid["spec"]["provider"]["kubernetes"]["envoyService"]["sourceRanges"] = [
            "0.0.0.0/0"
        ]
        invalid_examples.append(invalid)
        invalid = copy.deepcopy(config)
        invalid["spec"]["provider"]["kubernetes"]["envoyService"][
            "allocateLoadBalancerNodePorts"
        ] = "false"
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
        classes = {
            item["metadata"]["name"]: item
            for item in self.resources_of_kind("GatewayClass")
        }
        allowed = {
            "private-home": {"10.0.40.42", "10.0.80.42", "10.0.100.42"},
            "private-admin": {"10.0.70.10", "10.0.80.42", "10.0.100.42"},
        }
        clients = {
            "10.0.30.42",
            "10.0.40.42",
            "10.0.50.42",
            "10.0.60.42",
            "10.0.70.10",
            "10.0.70.11",
            "10.0.70.42",
            "10.0.80.42",
            "10.0.90.42",
            "10.0.100.42",
            "10.244.1.42",
            "192.0.2.42",
        }
        for config in self.resources_of_kind("EnvoyProxy"):
            name = config["metadata"]["name"]
            service = config["spec"]["provider"]["kubernetes"]["envoyService"]
            ranges = [
                ipaddress.ip_network(cidr)
                for cidr in service["loadBalancerSourceRanges"]
            ]
            admitted = {
                client
                for client in clients
                if any(ipaddress.ip_address(client) in net for net in ranges)
            }
            self.assertEqual(admitted, allowed[name])
            self.assertFalse(service["allocateLoadBalancerNodePorts"])
            self.assertEqual(service["externalTrafficPolicy"], "Local")
            self.assertEqual(config["spec"]["ipFamily"], "IPv4")
        for gateway in self.resources_of_kind("Gateway"):
            namespace = gateway["metadata"]["namespace"]
            parameters = classes[gateway["spec"]["gatewayClassName"]]["spec"][
                "parametersRef"
            ]
            self.assertEqual(parameters["kind"], "EnvoyProxy")
            self.assertEqual(parameters["group"], "gateway.envoyproxy.io")
            self.assertEqual(
                classes[gateway["spec"]["gatewayClassName"]]["spec"]["controllerName"],
                "gateway.envoyproxy.io/gatewayclass-controller",
            )
            self.assertEqual(
                (parameters["namespace"], parameters["name"]), (namespace, namespace)
            )

    def test_ip_allocation_and_announcements_require_exact_service_identity(self):
        pools = self.resources_of_kind("IPAddressPool")
        proxies = {
            item["metadata"]["name"]: item
            for item in self.resources_of_kind("EnvoyProxy")
        }
        self.assertEqual(len(pools), 2)
        addresses: set[str] = set()
        for pool in pools:
            name = pool["metadata"]["name"]
            self.assertEqual(pool["metadata"]["namespace"], "metallb-system")
            self.assertFalse(pool["spec"]["autoAssign"])
            allocation = pool["spec"]["serviceAllocation"]
            self.assertEqual(allocation["namespaces"], [name])
            self.assertEqual(
                allocation["serviceSelectors"],
                [
                    {
                        "matchLabels": {
                            "app.kubernetes.io/managed-by": "envoy-gateway",
                            "app.kubernetes.io/component": "proxy",
                            "gateway.envoyproxy.io/owning-gateway-name": name,
                            "gateway.envoyproxy.io/owning-gateway-namespace": name,
                        }
                    }
                ],
            )
            network = ipaddress.ip_network(pool["spec"]["addresses"][0])
            self.assertEqual(network.prefixlen, 32)
            addresses.add(str(network.network_address))
            service = proxies[name]["spec"]["provider"]["kubernetes"]["envoyService"]
            self.assertEqual(service["loadBalancerClass"], "metallb.io/metallb")
            self.assertEqual(
                service["annotations"],
                {
                    "metallb.io/address-pool": name,
                    "metallb.io/loadBalancerIPs": str(network.network_address),
                },
            )
            self.assertEqual(service["name"], "envoy-" + name)
        self.assertEqual(addresses, {"10.0.70.200", "10.0.70.201"})
        advertisements = self.resources_of_kind("L2Advertisement")
        self.assertEqual(len(advertisements), 1)
        self.assertEqual(
            advertisements[0]["spec"],
            {
                "ipAddressPools": ["private-home", "private-admin"],
                "nodeSelectors": [
                    {"matchLabels": {"kubernetes.io/hostname": "talos-2jn-7he"}},
                    {"matchLabels": {"kubernetes.io/hostname": "talos-p5e-e9e"}},
                ],
                "interfaces": ["eno1"],
            },
        )

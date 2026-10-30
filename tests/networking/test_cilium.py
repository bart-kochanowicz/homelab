from .support import GatewayTestCase


class CiliumTests(GatewayTestCase):
    def test_cilium_keeps_the_existing_dataplane_and_host_firewall(self):
        config = next(
            item
            for item in self.rendered("helm-cilium.yaml")
            if item["kind"] == "ConfigMap"
            and item["metadata"]["name"] == "cilium-config"
        )
        data = config["data"]
        for key in (
            "kube-proxy-replacement",
            "enable-host-firewall",
            "enable-host-legacy-routing",
            "bpf-lb-sock-hostns-only",
            "bpf-lb-source-range-all-types",
        ):
            self.assertEqual(data[key], "true", key)
        self.assertEqual(data.get("enable-gateway-api", "false"), "false")
        self.assertEqual(data["routing-mode"], "tunnel")
        self.assertEqual(data.get("enable-l2-announcements", "false"), "false")
        self.assertEqual(data["default-lb-service-ipam"], "none")
        self.assertFalse(
            any(
                item["kind"]
                in {"CiliumLoadBalancerIPPool", "CiliumL2AnnouncementPolicy"}
                for item in self.resources
            )
        )

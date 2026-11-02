from .support import GatewayTestCase


class CiliumTests(GatewayTestCase):
    def test_houston_backup_can_reach_only_the_control_plane_talos_api(self):
        policy = next(
            item
            for item in self.rendered("system-network-policies.yaml")
            if item["kind"] == "CiliumClusterwideNetworkPolicy"
            and item["metadata"]["name"] == "homelab-talos-backup-access"
        )
        self.assertEqual(
            policy["spec"]["nodeSelector"]["matchLabels"],
            {"node-role.kubernetes.io/control-plane": ""},
        )
        self.assertEqual(
            policy["spec"]["ingress"],
            [
                {
                    "fromCIDR": ["10.0.70.10/32"],
                    "toPorts": [{"ports": [{"port": "50000", "protocol": "TCP"}]}],
                }
            ],
        )

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

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .support import ROOT, GatewayTestCase


class HomeAssistantGatewayTests(GatewayTestCase):
    def test_home_assistant_route_only_uses_its_private_home_listener_and_service(self):
        resources = self.rendered("apps-home-assistant.yaml")
        routes = [item for item in resources if item["kind"] == "HTTPRoute"]
        self.assertEqual(len(routes), 1)
        route = routes[0]
        self.assertEqual(route["metadata"]["namespace"], "home-assistant")
        spec = route["spec"]
        self.assertEqual(
            spec["parentRefs"],
            [
                {
                    "name": "private-home",
                    "namespace": "private-home",
                    "sectionName": "home-assistant",
                }
            ],
        )
        self.assertEqual(spec["hostnames"], ["ha.thecavespace.net"])
        self.assertEqual(len(spec["rules"]), 1)
        rule = spec["rules"][0]
        self.assertEqual(set(rule), {"matches", "backendRefs", "timeouts"})
        self.assertEqual(
            rule["matches"], [{"path": {"type": "PathPrefix", "value": "/"}}]
        )
        self.assertEqual(
            rule["backendRefs"], [{"name": "home-assistant", "port": 8123}]
        )
        self.assertEqual(rule["timeouts"], {"request": "0s"})
        service = next(
            item
            for item in resources
            if item["kind"] == "Service"
            and item["metadata"]["name"] == rule["backendRefs"][0]["name"]
        )
        self.assertEqual(
            service["metadata"]["namespace"], route["metadata"]["namespace"]
        )
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertIn(
            {"name": "https", "port": 8123, "targetPort": 8123, "protocol": "TCP"},
            service["spec"]["ports"],
        )

    def test_home_assistant_backend_tls_matches_the_mounted_certificate_and_probes(
        self,
    ):
        resources = self.rendered("apps-home-assistant.yaml")
        certificate = next(item for item in resources if item["kind"] == "Certificate")
        policy = next(item for item in resources if item["kind"] == "BackendTLSPolicy")
        service = next(item for item in resources if item["kind"] == "Service")
        deployment = next(item for item in resources if item["kind"] == "Deployment")
        config = next(item for item in resources if item["kind"] == "ConfigMap")
        self.assertEqual(
            policy["spec"]["targetRefs"],
            [
                {
                    "group": "",
                    "kind": "Service",
                    "name": service["metadata"]["name"],
                    "sectionName": service["spec"]["ports"][0]["name"],
                }
            ],
        )
        self.assertEqual(
            policy["spec"]["validation"],
            {
                "hostname": "ha.thecavespace.net",
                "wellKnownCACertificates": "System",
            },
        )
        self.assertEqual(
            set(certificate["spec"]["dnsNames"]),
            {
                policy["spec"]["validation"]["hostname"],
                "ha-backend.thecavespace.net",
            },
        )
        self.assertEqual(
            certificate["spec"]["issuerRef"]["name"], "letsencrypt-production"
        )
        self.assertEqual(certificate["spec"]["privateKey"]["rotationPolicy"], "Always")
        self.assertLess(
            int(certificate["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]),
            int(policy["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]),
        )
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]
        mount = next(
            item for item in container["volumeMounts"] if item["name"] == "backend-tls"
        )
        self.assertTrue(mount["readOnly"])
        self.assertFalse({"subPath", "subPathExpr"} & set(mount))
        volume = next(item for item in pod["volumes"] if item["name"] == mount["name"])
        secret = certificate["spec"]["secretName"]
        self.assertEqual(volume["secret"], {"secretName": secret, "defaultMode": 0o400})
        self.assertEqual(
            deployment["metadata"]["annotations"][
                "secret.reloader.stakater.com/reload"
            ],
            secret,
        )
        self.assertEqual(deployment["spec"]["strategy"], {"type": "Recreate"})
        for probe in ("livenessProbe", "readinessProbe"):
            self.assertEqual(container[probe]["httpGet"]["scheme"], "HTTPS")
            port = next(
                item
                for item in container["ports"]
                if item["name"] == container[probe]["httpGet"]["port"]
            )
            self.assertEqual(
                port["containerPort"], service["spec"]["ports"][0]["targetPort"]
            )
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as directory:
            fixture = Path(directory) / "configuration.yaml"
            fixture.write_text(config["data"]["configuration.yaml"])
            result = subprocess.run(
                ["yq", "-o=json", ".http", str(fixture)],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
        http = json.loads(result.stdout)
        self.assertEqual(http["ssl_certificate"], mount["mountPath"] + "/tls.crt")
        self.assertEqual(http["ssl_key"], mount["mountPath"] + "/tls.key")

    def test_home_assistant_host_access_requires_home_proxy_identity(self):
        policies = self.rendered("system-network-policies.yaml")
        host = next(
            item
            for item in policies
            if item["kind"] == "CiliumClusterwideNetworkPolicy"
            and item["metadata"]["name"] == "homelab-host-firewall"
        )
        proxy_rules = [
            rule
            for rule in host["spec"]["ingress"]
            if any(
                selector.get("matchLabels", {}).get("k8s:io.kubernetes.pod.namespace")
                == "private-home"
                for selector in rule.get("fromEndpoints", [])
            )
        ]
        self.assertEqual(len(proxy_rules), 1)
        rule = proxy_rules[0]
        self.assertEqual(set(rule), {"fromEndpoints", "toPorts"})
        self.assertEqual(
            rule["fromEndpoints"],
            [
                {
                    "matchLabels": {
                        "k8s:io.kubernetes.pod.namespace": "private-home",
                        "k8s:app.kubernetes.io/managed-by": "envoy-gateway",
                        "k8s:app.kubernetes.io/component": "proxy",
                        "k8s:gateway.envoyproxy.io/owning-gateway-name": "private-home",
                    }
                }
            ],
        )
        ports = [{"ports": [{"port": "8123", "protocol": "TCP"}]}]
        self.assertEqual(rule["toPorts"], ports)
        home = next(
            item
            for item in policies
            if item["kind"] == "CiliumNetworkPolicy"
            and item["metadata"]["name"] == "private-proxy"
            and item["metadata"]["namespace"] == "private-home"
        )
        self.assertEqual(
            home["spec"]["endpointSelector"],
            {
                "matchLabels": {
                    "app.kubernetes.io/managed-by": "envoy-gateway",
                    "app.kubernetes.io/component": "proxy",
                    "gateway.envoyproxy.io/owning-gateway-name": "private-home",
                }
            },
        )
        node_rules = [rule for rule in home["spec"]["egress"] if "toEntities" in rule]
        self.assertEqual(
            node_rules, [{"toEntities": ["host", "remote-node"], "toPorts": ports}]
        )

    def home_assistant_configuration(self, config: dict[str, Any]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as directory:
            fixture = Path(directory) / "configuration.yaml"
            fixture.write_text(config["data"]["configuration.yaml"])
            result = subprocess.run(
                ["yq", "-o=json", ".", str(fixture)],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
        return json.loads(result.stdout)

    def front_door_configuration(self) -> dict[str, Any]:
        config = next(
            item
            for item in self.rendered("apps-home-assistant.yaml")
            if item["kind"] == "ConfigMap"
        )
        return self.home_assistant_configuration(config)

    def test_camera_snapshot_is_a_raw_jpeg_mqtt_image_on_a_topic_the_camera_may_write(
        self,
    ):
        configuration = self.front_door_configuration()
        self.assertEqual(
            configuration["mqtt"]["image"],
            [
                {
                    "name": "Front door camera snapshot",
                    "unique_id": "front_door_camera_snapshot",
                    "image_topic": "doorview/front-door-camera/snapshot",
                    "content_type": "image/jpeg",
                    "encoding": "",
                }
            ],
        )
        broker = next(
            item
            for item in self.rendered("apps-mosquitto.yaml")
            if item["kind"] == "ConfigMap"
        )
        self.assertIn(
            "topic write doorview/front-door-camera/#",
            broker["data"]["acl"].splitlines(),
        )
        self.assertIn("max_packet_size 65536", broker["data"]["mosquitto.conf"])
        # The snapshot needs no credentials, router rule or Secret of its own.
        text = json.dumps(configuration)
        self.assertNotIn("10.0.50.190", text)
        self.assertNotIn("shell_command", configuration)

    def test_motion_automation_waits_for_a_fresh_snapshot_and_is_rate_limited(self):
        automations = self.front_door_configuration()["automation front_door"]
        self.assertEqual(len(automations), 1)
        automation = automations[0]
        self.assertEqual(automation["mode"], "single")
        self.assertEqual(automation["max_exceeded"], "silent")
        self.assertEqual(
            automation["triggers"],
            [
                {
                    "trigger": "state",
                    "entity_id": "binary_sensor.front_door_camera_motion",
                    "from": "off",
                    "to": "on",
                }
            ],
        )
        image = "image.front_door_camera_snapshot"
        actions = automation["actions"]
        wait = actions[0]["then"][0]
        self.assertEqual(
            wait["wait_for_trigger"],
            [{"trigger": "state", "entity_id": image}],
        )
        self.assertEqual(wait["timeout"], "00:00:20")
        self.assertTrue(wait["continue_on_timeout"])
        choice = actions[2]["choose"][0]
        self.assertIn("snapshot_is_new", choice["conditions"])
        data = choice["sequence"][0]["data"]["data"]
        self.assertEqual(data["image"], f"/api/image_proxy/{image}")
        self.assertEqual(data["attachment"], {"url": f"/api/image_proxy/{image}"})
        self.assertNotIn("data", actions[2]["default"][0]["data"])
        # The run holds the single slot for the cooldown, so repeated motion is dropped.
        self.assertEqual(actions[-1], {"delay": "00:01:00"})

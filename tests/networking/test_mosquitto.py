import re

from .support import GatewayTestCase

CAMERA = "10.0.50.190"
HOME_ASSISTANT_WORKER = "10.0.70.12"
BROKER_VIP = "10.0.70.202"


class MosquittoTests(GatewayTestCase):
    def broker_resources(self):
        return self.rendered("apps-mosquitto.yaml")

    def test_broker_runs_unprivileged_from_a_pinned_image(self):
        deployment = next(
            item for item in self.broker_resources() if item["kind"] == "Deployment"
        )
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]
        self.assertEqual(deployment["spec"]["replicas"], 1)
        self.assertEqual(deployment["spec"]["strategy"], {"type": "Recreate"})
        self.assertRegex(
            container["image"],
            r"^docker\.io/library/eclipse-mosquitto:\d+\.\d+\.\d+-alpine@sha256:[0-9a-f]{64}$",
        )
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(
            pod["securityContext"],
            {
                "runAsNonRoot": True,
                "runAsUser": 1883,
                "runAsGroup": 1883,
                "fsGroup": 1883,
                "fsGroupChangePolicy": "OnRootMismatch",
                "seccompProfile": {"type": "RuntimeDefault"},
            },
        )
        self.assertEqual(
            container["securityContext"],
            {
                "allowPrivilegeEscalation": False,
                "readOnlyRootFilesystem": True,
                "capabilities": {"drop": ["ALL"]},
            },
        )
        self.assertEqual(
            container["ports"],
            [{"name": "mqtt", "containerPort": 1883, "protocol": "TCP"}],
        )
        for probe in ("startupProbe", "livenessProbe", "readinessProbe"):
            self.assertEqual(container[probe]["tcpSocket"], {"port": "mqtt"})
        self.assertIn("requests", container["resources"])
        self.assertIn("limits", container["resources"])
        self.assertNotIn("hostNetwork", pod)
        self.assertNotIn("hostPath", {key for v in pod["volumes"] for key in v})

    def test_broker_requires_authentication_and_limits_the_camera_to_its_own_topics(
        self,
    ):
        resources = self.broker_resources()
        config = next(item for item in resources if item["kind"] == "ConfigMap")
        deployment = next(item for item in resources if item["kind"] == "Deployment")
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]
        settings = config["data"]["mosquitto.conf"].splitlines()
        self.assertEqual(
            [line for line in settings if line.startswith("listener")],
            ["listener 1883"],
        )
        self.assertIn("allow_anonymous false", settings)
        self.assertIn("persistence false", settings)
        self.assertNotIn("allow_anonymous true", settings)
        self.assertIn("acl_file /mosquitto/config/acl", settings)
        self.assertIn("password_file /mosquitto/secret/passwd", settings)

        acl = [
            line.strip() for line in config["data"]["acl"].splitlines() if line.strip()
        ]
        self.assertEqual(
            acl,
            [
                "user home-assistant",
                "topic readwrite #",
                "user front-door-camera",
                "topic write doorview/front-door-camera/#",
                "topic write homeassistant/sensor/front-door-camera/+/config",
                "topic write homeassistant/binary_sensor/front-door-camera/+/config",
                "topic write homeassistant/event/front-door-camera/+/config",
            ],
        )

        mounts = {item["name"]: item for item in container["volumeMounts"]}
        volumes = {item["name"]: item for item in pod["volumes"]}
        self.assertEqual(
            {
                name: (item["mountPath"], item["readOnly"])
                for name, item in mounts.items()
            },
            {
                "config": ("/mosquitto/config", True),
                "secret": ("/mosquitto/secret", True),
            },
        )
        self.assertEqual(
            volumes["config"]["configMap"],
            {"name": "mosquitto-config", "defaultMode": 0o440},
        )
        self.assertEqual(
            volumes["secret"]["secret"],
            {"secretName": "mosquitto-secret", "defaultMode": 0o440},
        )
        # Only the sealed password file may be committed, never a plaintext Secret.
        self.assertFalse(any(item["kind"] == "Secret" for item in resources))
        sealed = [item for item in resources if item["kind"] == "SealedSecret"]
        self.assertEqual(len(sealed), 1)
        self.assertEqual(sealed[0]["metadata"]["name"], "mosquitto-secret")
        self.assertEqual(sealed[0]["metadata"]["namespace"], "mosquitto")
        self.assertEqual(list(sealed[0]["spec"]["encryptedData"]), ["passwd"])
        self.assertNotIn("stringData", sealed[0]["spec"]["template"])
        self.assertNotIn("data", sealed[0]["spec"]["template"])

    def test_broker_vip_is_allocated_only_to_the_broker_service(self):
        service = next(
            item for item in self.broker_resources() if item["kind"] == "Service"
        )
        pool = next(
            item
            for item in self.resources_of_kind("IPAddressPool")
            if item["metadata"]["name"] == "mosquitto"
        )
        announcement = self.resources_of_kind("L2Advertisement")[0]
        self.assertEqual(pool["metadata"]["namespace"], "metallb-system")
        self.assertEqual(pool["spec"]["addresses"], [BROKER_VIP + "/32"])
        self.assertFalse(pool["spec"]["autoAssign"])
        allocation = pool["spec"]["serviceAllocation"]
        self.assertEqual(allocation["namespaces"], ["mosquitto"])
        self.assertEqual(len(allocation["serviceSelectors"]), 1)
        selector = allocation["serviceSelectors"][0]["matchLabels"]
        self.assertEqual(
            selector,
            {
                "app.kubernetes.io/name": "mosquitto",
                "app.kubernetes.io/part-of": "homelab",
            },
        )
        self.assertEqual(service["metadata"]["namespace"], "mosquitto")
        self.assertLessEqual(selector.items(), service["metadata"]["labels"].items())
        self.assertEqual(
            service["metadata"]["annotations"],
            {
                "metallb.io/address-pool": "mosquitto",
                "metallb.io/loadBalancerIPs": BROKER_VIP,
            },
        )
        spec = service["spec"]
        self.assertEqual(spec["type"], "LoadBalancer")
        self.assertEqual(spec["loadBalancerClass"], "metallb.io/metallb")
        self.assertFalse(spec["allocateLoadBalancerNodePorts"])
        # Local keeps the camera's source address, which the pod policy matches.
        self.assertEqual(spec["externalTrafficPolicy"], "Local")
        self.assertEqual(
            spec["loadBalancerSourceRanges"],
            [CAMERA + "/32", HOME_ASSISTANT_WORKER + "/32"],
        )
        self.assertEqual(
            spec["ports"],
            [{"name": "mqtt", "port": 1883, "targetPort": "mqtt", "protocol": "TCP"}],
        )
        self.assertIn("mosquitto", announcement["spec"]["ipAddressPools"])

    def test_only_the_camera_and_home_assistant_reach_the_broker(self):
        policies = self.rendered("system-network-policies.yaml")
        in_namespace = [
            item
            for item in policies
            if item["metadata"].get("namespace") == "mosquitto"
        ]
        deny = next(item for item in in_namespace if item["kind"] == "NetworkPolicy")
        self.assertEqual(deny["metadata"]["name"], "default-deny")
        self.assertEqual(deny["spec"]["podSelector"], {})
        self.assertEqual(deny["spec"]["policyTypes"], ["Ingress", "Egress"])
        allow = next(
            item for item in in_namespace if item["kind"] == "CiliumNetworkPolicy"
        )
        self.assertEqual(
            allow["spec"]["endpointSelector"],
            {"matchLabels": {"app.kubernetes.io/name": "mosquitto"}},
        )
        port = [{"ports": [{"port": "1883", "protocol": "TCP"}]}]
        self.assertEqual(
            allow["spec"]["ingress"],
            [
                {"fromCIDR": [CAMERA + "/32"], "toPorts": port},
                {"fromEntities": ["host", "remote-node"], "toPorts": port},
            ],
        )
        self.assertNotIn("egress", allow["spec"])
        self.assertNotIn("ingressDeny", allow["spec"])

    def test_namespace_and_project_admit_exactly_the_broker_resources(self):
        namespace = next(
            item
            for item in self.rendered("system-app-namespaces.yaml")
            if item["kind"] == "Namespace" and item["metadata"]["name"] == "mosquitto"
        )
        labels = namespace["metadata"]["labels"]
        self.assertEqual(labels["pod-security.kubernetes.io/enforce"], "restricted")
        self.assertEqual(labels["pod-security.kubernetes.io/audit"], "restricted")
        self.assertEqual(labels["pod-security.kubernetes.io/warn"], "restricted")
        self.assertEqual(
            namespace["metadata"]["annotations"]["argocd.argoproj.io/sync-options"],
            "Prune=false,Delete=false",
        )
        project = next(
            item
            for item in self.rendered("system-argocd.yaml")
            if item["kind"] == "AppProject"
            and item["metadata"]["name"] == "applications"
        )
        self.assertIn(
            {"namespace": "mosquitto", "server": "https://kubernetes.default.svc"},
            project["spec"]["destinations"],
        )
        platform = next(
            item
            for item in self.rendered("system-argocd.yaml")
            if item["kind"] == "AppProject" and item["metadata"]["name"] == "platform"
        )
        # The network-policies application belongs to the platform project.
        self.assertIn(
            {"namespace": "mosquitto", "server": "https://kubernetes.default.svc"},
            platform["spec"]["destinations"],
        )
        allowed = {
            (item["group"], item["kind"])
            for item in project["spec"]["namespaceResourceWhitelist"]
        }
        groups = {
            "ConfigMap": "",
            "Service": "",
            "ServiceAccount": "",
            "Deployment": "apps",
            "SealedSecret": "bitnami.com",
        }
        for item in self.broker_resources():
            self.assertIn((groups[item["kind"]], item["kind"]), allowed)
            self.assertEqual(item["metadata"]["namespace"], "mosquitto")
            self.assertRegex(
                item["metadata"]["name"], re.compile(r"^mosquitto(-config|-secret)?$")
            )

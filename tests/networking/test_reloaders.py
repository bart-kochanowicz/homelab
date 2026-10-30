from .support import GatewayTestCase


class ReloaderTests(GatewayTestCase):
    def test_reloaders_are_namespaced_and_can_only_patch_their_application(self):
        for namespace in ("home-assistant", "n8n"):
            with self.subTest(namespace=namespace):
                resources = self.rendered(f"helm-{namespace}-reloader.yaml")
                self.assertFalse(
                    any(
                        item["kind"] in {"ClusterRole", "ClusterRoleBinding"}
                        for item in resources
                    )
                )
                self.assertTrue(
                    all(
                        item["metadata"]["namespace"] == namespace for item in resources
                    )
                )
                deployment = next(
                    item for item in resources if item["kind"] == "Deployment"
                )
                role = next(item for item in resources if item["kind"] == "Role")
                binding = next(
                    item for item in resources if item["kind"] == "RoleBinding"
                )
                pod = deployment["spec"]["template"]["spec"]
                self.assertEqual(binding["roleRef"]["name"], role["metadata"]["name"])
                self.assertEqual(
                    binding["subjects"],
                    [
                        {
                            "kind": "ServiceAccount",
                            "name": pod["serviceAccountName"],
                            "namespace": namespace,
                        }
                    ],
                )
                writes = [
                    rule
                    for rule in role["rules"]
                    if "apps" in rule["apiGroups"]
                    and set(rule["verbs"]) - {"get", "list", "watch"}
                ]
                self.assertEqual(
                    writes,
                    [
                        {
                            "apiGroups": ["apps"],
                            "resources": ["deployments"],
                            "resourceNames": [namespace],
                            "verbs": ["patch"],
                        }
                    ],
                )
                for rule in role["rules"]:
                    self.assertFalse(
                        any(
                            "*" in rule[field]
                            for field in ("apiGroups", "resources", "verbs")
                        )
                    )
                    if "secrets" in rule["resources"]:
                        self.assertEqual(set(rule["verbs"]), {"get", "list", "watch"})
                    if "configmaps" in rule["resources"] and "update" in rule["verbs"]:
                        self.assertEqual(rule["resourceNames"], ["reloader-meta-info"])
                container = pod["containers"][0]
                args = container["args"]
                for flag in (
                    "--resources-to-ignore=configmaps",
                    "--ignored-workload-types=jobs,cronjobs",
                    "--reload-strategy=env-vars",
                    "--reload-on-create=true",
                    "--sync-after-restart=true",
                ):
                    self.assertIn(flag, args)
                self.assertNotIn("--auto-reload-all=true", args)
                namespace_env = next(
                    item
                    for item in container["env"]
                    if item["name"] == "KUBERNETES_NAMESPACE"
                )
                self.assertEqual(
                    namespace_env["valueFrom"]["fieldRef"]["fieldPath"],
                    "metadata.namespace",
                )
                certificate = next(
                    item
                    for item in self.rendered(f"apps-{namespace}.yaml")
                    if item["kind"] == "Certificate"
                )
                labels = certificate["spec"]["secretTemplate"]["labels"]
                self.assertIn(
                    "--resource-label-selector="
                    + ",".join(f"{key}={value}" for key, value in labels.items()),
                    args,
                )
                policy = next(
                    item
                    for item in self.rendered("system-network-policies.yaml")
                    if item["metadata"]["name"] == f"{namespace}-reloader"
                )
                for key, value in policy["spec"]["endpointSelector"][
                    "matchLabels"
                ].items():
                    self.assertEqual(
                        deployment["spec"]["template"]["metadata"]["labels"][key], value
                    )
                self.assertEqual(
                    policy["spec"]["egress"][0],
                    {
                        "toEntities": ["kube-apiserver"],
                        "toPorts": [{"ports": [{"port": "6443", "protocol": "TCP"}]}],
                    },
                )
                self.assertEqual(len(policy["spec"]["egress"]), 2)
                self.assertNotIn("ingress", policy["spec"])

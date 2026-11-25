import re

import yaml

from .support import ROOT, GatewayTestCase


def chart_version() -> str:
    chart = yaml.safe_load((ROOT / "system/metallb/Chart.yaml").read_text())
    return next(
        str(dependency["version"])
        for dependency in chart["dependencies"]
        if dependency["name"] == "metallb"
    )


class MetalLBTests(GatewayTestCase):
    def test_metallb_only_runs_l2_with_a_dedicated_service_class(self):
        resources = self.rendered("helm-metallb.yaml")
        workloads = [
            item for item in resources if item["kind"] in {"Deployment", "DaemonSet"}
        ]
        self.assertEqual(
            {item["metadata"]["name"] for item in workloads},
            {"metallb-controller", "metallb-speaker"},
        )
        for workload in workloads:
            pod = workload["spec"]["template"]["spec"]
            self.assertFalse(pod.get("initContainers"))
            self.assertEqual(len(pod["containers"]), 1)
            container = pod["containers"][0]
            self.assertIn("--lb-class=metallb.io/metallb", container["args"])
            # Images match the chart release and are pinned by digest.
            self.assertRegex(
                container["image"],
                rf":v{re.escape(chart_version())}@sha256:[0-9a-f]{{64}}$",
            )
            self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
            self.assertEqual(
                container["securityContext"]["capabilities"]["drop"], ["ALL"]
            )
            secret_envs = {
                env["name"]: env.get("value")
                for env in container.get("env", [])
                if "SECRET" in env["name"]
            }
            if workload["kind"] == "DaemonSet":
                self.assertTrue(pod["hostNetwork"])
                self.assertIn("--ignore-exclude-lb", container["args"])
                self.assertEqual(
                    container["securityContext"]["capabilities"]["add"], ["NET_RAW"]
                )
                self.assertEqual(
                    secret_envs, {"METALLB_ML_SECRET_KEY_PATH": "/etc/ml_secret_key"}
                )
                self.assertIn(
                    {
                        "name": "memberlist",
                        "secret": {
                            "secretName": "metallb-memberlist",
                            "defaultMode": 420,
                        },
                    },
                    pod["volumes"],
                )
            else:
                self.assertEqual(
                    secret_envs, {"METALLB_ML_SECRET_NAME": "metallb-memberlist"}
                )

    def test_metallb_crds_and_configuration_have_separate_manual_owners(self):
        controller = self.rendered("helm-metallb.yaml")
        definitions = self.rendered("system-metallb-crds.yaml")
        self.assertFalse(
            any(item["kind"] == "CustomResourceDefinition" for item in controller)
        )
        self.assertEqual(len(definitions), 9)
        # The CRDs come from the same MetalLB release as the controller chart.
        sources = yaml.safe_load(
            (ROOT / "system/metallb-crds/kustomization.yaml").read_text()
        )["resources"]
        self.assertEqual(len(sources), 9)
        for source in sources:
            self.assertIn(f"/metallb/metallb/v{chart_version()}/config/crd/", source)
        for item in definitions:
            self.assertEqual(item["kind"], "CustomResourceDefinition")
            self.assertEqual(item["spec"]["group"], "metallb.io")
            self.assertEqual(
                item["metadata"]["annotations"]["argocd.argoproj.io/sync-options"],
                "Prune=false,Delete=false",
            )
        argocd = self.rendered("system-argocd.yaml")
        apps = [
            item
            for item in argocd
            if item["kind"] == "Application"
            and item["metadata"]["name"]
            in {"metallb", "metallb-crds", "metallb-config"}
        ]
        self.assertEqual(len(apps), 3)
        for app in apps:
            self.assertNotIn("automated", app["spec"]["syncPolicy"])
            self.assertNotIn("finalizers", app["metadata"])
            self.assertIn(
                "FailOnSharedResource=true", app["spec"]["syncPolicy"]["syncOptions"]
            )
        applications = next(
            item
            for item in argocd
            if item["kind"] == "AppProject"
            and item["metadata"]["name"] == "applications"
        )
        self.assertFalse(
            any(
                item["group"] == "metallb.io"
                for item in applications["spec"]["namespaceResourceWhitelist"]
            )
        )

    def test_metallb_upstream_wildcard_verbs_are_limited_to_status_resources(self):
        for item in self.rendered("helm-metallb.yaml"):
            if item["kind"] not in {"Role", "ClusterRole"}:
                continue
            for rule in item["rules"]:
                self.assertNotIn("*", rule["apiGroups"])
                self.assertNotIn("*", rule["resources"])
                if "*" in rule["verbs"]:
                    self.assertEqual(rule["apiGroups"], ["metallb.io"])
                    self.assertLessEqual(
                        set(rule["resources"]),
                        {
                            "servicel2statuses",
                            "servicel2statuses/status",
                            "servicebgpstatuses",
                            "servicebgpstatuses/status",
                            "configurationstates",
                            "configurationstates/status",
                        },
                    )

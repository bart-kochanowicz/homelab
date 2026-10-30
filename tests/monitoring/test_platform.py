import json
import subprocess

from .support import ROOT, MonitoringTestCase


class MonitoringPlatformTests(MonitoringTestCase):
    def test_stateful_monitoring_uses_distinct_retained_nvme_claim_templates(self):
        for kind, name, size in (
            ("Prometheus", "prometheus-data-nvme", "50Gi"),
            ("Alertmanager", "alertmanager-data-nvme", "5Gi"),
        ):
            with self.subTest(kind=kind):
                resource = next(item for item in self.resources if item["kind"] == kind)
                spec = resource["spec"]
                self.assertFalse(spec.get("paused", False))
                self.assertEqual(
                    spec["persistentVolumeClaimRetentionPolicy"],
                    {
                        "whenDeleted": "Retain",
                        "whenScaled": "Retain",
                    },
                )
                claim = spec["storage"]["volumeClaimTemplate"]
                self.assertEqual(claim["metadata"]["name"], name)
                self.assertEqual(
                    claim["metadata"]["annotations"]["argocd.argoproj.io/sync-options"],
                    "Prune=false,Delete=false",
                )
                self.assertEqual(claim["spec"]["storageClassName"], "local-path-nvme")
                self.assertEqual(
                    claim["spec"]["resources"]["requests"]["storage"], size
                )
                self.assertEqual(spec["securityContext"]["runAsUser"], 1000)
                self.assertEqual(spec["securityContext"]["runAsGroup"], 2000)

    def test_replacement_alerts_are_rendered_instead_of_inapplicable_chart_rules(self):
        names = {
            rule["alert"]
            for resource in self.resources
            if resource["kind"] == "PrometheusRule"
            for group in resource["spec"]["groups"]
            for rule in (group.get("rules") or [])
            if "alert" in rule
        }
        self.assertFalse(
            names
            & {
                "KubeSchedulerDown",
                "KubeControllerManagerDown",
                "KubeCPUOvercommit",
                "KubeMemoryOvercommit",
                "CiliumPolicyDrops",
            }
        )
        self.assertTrue(
            {
                "TalosSchedulerUnavailable",
                "TalosControllerManagerUnavailable",
                "NodeMemoryRequestsHigh",
                "NodeCpuRequestsHigh",
                "CiliumUnexpectedDrops",
            }
            <= names
        )

    def test_cilium_monitors_match_the_pinned_chart_pods_and_ports(self):
        result = subprocess.run(
            [
                "yq",
                "-o=json",
                "-I=0",
                'select(.kind == "DaemonSet" or .kind == "Deployment")',
                str(ROOT / ".cache/rendered/helm-cilium.yaml"),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        workloads = [
            json.loads(line) for line in result.stdout.splitlines() if line.strip()
        ]
        for name in ("cilium-agent", "cilium-operator"):
            monitor = next(
                item
                for item in self.resources
                if item["kind"] == "PodMonitor" and item["metadata"]["name"] == name
            )
            selector = monitor["spec"]["selector"]["matchLabels"]
            matches = [
                workload["spec"]["template"]
                for workload in workloads
                if all(
                    workload["spec"]["template"]["metadata"]["labels"].get(key) == value
                    for key, value in selector.items()
                )
            ]
            self.assertEqual(len(matches), 1)
            labels = matches[0]["metadata"]["labels"]
            self.assertEqual(labels[monitor["spec"]["jobLabel"]], name)
            ports = {
                port["name"]
                for container in matches[0]["spec"]["containers"]
                for port in container.get("ports", [])
            }
            for endpoint in monitor["spec"]["podMetricsEndpoints"]:
                self.assertIn(endpoint["port"], ports)

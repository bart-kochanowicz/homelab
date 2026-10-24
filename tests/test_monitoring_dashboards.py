import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MONITORING = ROOT / "system/monitoring"


class MonitoringDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dashboards = {
            path.name: json.loads(path.read_text())
            for path in (MONITORING / "dashboards").glob("*.json")
        }
        result = subprocess.run(
            ["yq", "-o=json", "-I=0", "select(.kind != null)",
             str(ROOT / ".cache/rendered/system-monitoring.yaml")],
            capture_output=True, text=True, check=True,
        )
        cls.resources = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def test_dashboard_files_are_provisioned_without_a_second_copy(self):
        configmap = next(item for item in self.resources if
                         item["kind"] == "ConfigMap" and
                         item["metadata"]["name"] == "homelab-dashboards")
        self.assertEqual(configmap["metadata"]["namespace"], "monitoring")
        self.assertEqual(configmap["metadata"]["labels"]["grafana_dashboard"], "1")
        self.assertEqual(configmap["metadata"]["annotations"]["grafana_folder"],
                         "/tmp/dashboards/Homelab")
        self.assertEqual(set(configmap["data"]), set(self.dashboards))
        for name, dashboard in self.dashboards.items():
            self.assertEqual(json.loads(configmap["data"][name]), dashboard)
        provider = next(item for item in self.resources if item["kind"] == "ConfigMap"
                        and "provider.yaml" in item.get("data", {}))
        self.assertIn("foldersFromFilesStructure: true", provider["data"]["provider.yaml"])
        self.assertIn("allowUiUpdates: false", provider["data"]["provider.yaml"])
        grafana = next(item for item in self.resources if item["kind"] == "Deployment"
                       and item["metadata"]["name"] == "kube-prometheus-stack-grafana")
        sidecar = next(item for item in grafana["spec"]["template"]["spec"]["containers"]
                       if item["name"] == "grafana-sc-dashboard")
        env = {entry["name"]: entry.get("value") for entry in sidecar["env"]}
        self.assertEqual(env["FOLDER_ANNOTATION"], "grafana_folder")

    def test_uids_and_datasources_match_the_provisioned_instance(self):
        uids = [dashboard["uid"] for dashboard in self.dashboards.values()]
        self.assertEqual(len(uids), len(set(uids)))
        other_uids = set()
        for resource in self.resources:
            if resource["kind"] != "ConfigMap" or resource["metadata"]["name"] == "homelab-dashboards":
                continue
            for name, content in resource.get("data", {}).items():
                if name.endswith(".json"):
                    other_uids.add(json.loads(content).get("uid"))
        self.assertFalse(set(uids) & other_uids, "A dashboard would overwrite an existing UID")
        for dashboard in self.dashboards.values():
            self.assertNotIn("__inputs", dashboard)
            self.assertFalse(dashboard["editable"])
            ids = [panel["id"] for panel in dashboard["panels"]]
            self.assertEqual(len(ids), len(set(ids)))
            for panel in dashboard["panels"]:
                self.assertEqual(panel["datasource"], {"type": "prometheus", "uid": "prometheus"})
                for link in dashboard["links"]:
                    if link["url"].startswith("/d/"):
                        self.assertIn(link["url"][3:], uids)

    def test_all_dashboard_queries_are_valid_promql(self):
        rules = []
        for dashboard in self.dashboards.values():
            for panel in dashboard["panels"]:
                for target in panel["targets"]:
                    expression = target["expr"].replace("$__rate_interval", "5m").replace("$namespace", ".*")
                    self.assertNotIn("$", expression)
                    rules.append({"record": f"dashboard_query_{len(rules)}", "expr": expression})
        with tempfile.TemporaryDirectory(prefix="dashboard-promql-") as directory:
            path = Path(directory) / "rules.json"
            path.write_text(json.dumps({"groups": [{"name": "dashboards", "rules": rules}]}))
            result = subprocess.run(["promtool", "check", "rules", str(path)],
                                    capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_replacement_alerts_are_rendered_instead_of_inapplicable_chart_rules(self):
        names = {rule["alert"] for resource in self.resources if resource["kind"] == "PrometheusRule"
                 for group in resource["spec"]["groups"] for rule in (group.get("rules") or []) if "alert" in rule}
        self.assertFalse(names & {"KubeSchedulerDown", "KubeControllerManagerDown",
                                  "KubeCPUOvercommit", "KubeMemoryOvercommit", "CiliumPolicyDrops"})
        self.assertTrue({"TalosSchedulerUnavailable", "TalosControllerManagerUnavailable",
                         "NodeMemoryRequestsHigh", "NodeCpuRequestsHigh", "CiliumUnexpectedDrops"} <= names)

    def test_cilium_monitors_match_the_pinned_chart_pods_and_ports(self):
        result = subprocess.run(
            ["yq", "-o=json", "-I=0", "select(.kind == \"DaemonSet\" or .kind == \"Deployment\")",
             str(ROOT / ".cache/rendered/helm-cilium.yaml")],
            capture_output=True, text=True, check=True,
        )
        workloads = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        for name in ("cilium-agent", "cilium-operator"):
            monitor = next(item for item in self.resources if item["kind"] == "PodMonitor"
                           and item["metadata"]["name"] == name)
            selector = monitor["spec"]["selector"]["matchLabels"]
            matches = [workload["spec"]["template"] for workload in workloads
                       if all(workload["spec"]["template"]["metadata"]["labels"].get(key) == value
                              for key, value in selector.items())]
            self.assertEqual(len(matches), 1)
            labels = matches[0]["metadata"]["labels"]
            self.assertEqual(labels[monitor["spec"]["jobLabel"]], name)
            ports = {port["name"] for container in matches[0]["spec"]["containers"]
                     for port in container.get("ports", [])}
            for endpoint in monitor["spec"]["podMetricsEndpoints"]:
                self.assertIn(endpoint["port"], ports)

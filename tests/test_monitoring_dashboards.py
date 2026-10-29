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

    def test_stateful_monitoring_uses_distinct_retained_nvme_claim_templates(self):
        for kind, name, size in (("Prometheus", "prometheus-data-nvme", "50Gi"),
                                 ("Alertmanager", "alertmanager-data-nvme", "5Gi")):
            with self.subTest(kind=kind):
                resource = next(item for item in self.resources if item["kind"] == kind)
                spec = resource["spec"]
                self.assertFalse(spec.get("paused", False))
                self.assertEqual(spec["persistentVolumeClaimRetentionPolicy"], {
                    "whenDeleted": "Retain", "whenScaled": "Retain",
                })
                claim = spec["storage"]["volumeClaimTemplate"]
                self.assertEqual(claim["metadata"]["name"], name)
                self.assertEqual(claim["metadata"]["annotations"]["argocd.argoproj.io/sync-options"],
                                 "Prune=false,Delete=false")
                self.assertEqual(claim["spec"]["storageClassName"], "local-path-nvme")
                self.assertEqual(claim["spec"]["resources"]["requests"]["storage"], size)
                self.assertEqual(spec["securityContext"]["runAsUser"], 1000)
                self.assertEqual(spec["securityContext"]["runAsGroup"], 2000)

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
                    self.assertNotIn("$", expression.replace("$1", ""))
                    rules.append({"record": f"dashboard_query_{len(rules)}", "expr": expression})
        with tempfile.TemporaryDirectory(prefix="dashboard-promql-") as directory:
            path = Path(directory) / "rules.json"
            path.write_text(json.dumps({"groups": [{"name": "dashboards", "rules": rules}]}))
            result = subprocess.run(["promtool", "check", "rules", str(path)],
                                    capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_node_label_allowlist_is_rendered_for_kube_state_metrics(self):
        deployment = next(item for item in self.resources if item["kind"] == "Deployment"
                          and item["metadata"]["name"] == "kube-prometheus-stack-kube-state-metrics")
        args = deployment["spec"]["template"]["spec"]["containers"][0]["args"]
        self.assertIn("--metric-labels-allowlist=nodes=[homelab.thecavespace.net/name]", args)

    def test_node_panels_preserve_values_with_aliases_and_unlabelled_nodes(self):
        groups = next(item["spec"]["groups"] for item in self.resources
                      if item["kind"] == "PrometheusRule"
                      and item["metadata"]["name"] == "homelab-security-and-operations")
        series = []
        for node, instance in (("talos-control", "10.0.70.11:9100"),
                               ("talos-worker", "10.0.70.12:9100")):
            for metric, labels, values in (
                ("kube_node_info", f'node="{node}"', "1+0x10"),
                ("kube_node_status_allocatable", f'node="{node}",resource="cpu"', "4+0x10"),
                ("kube_node_status_allocatable", f'node="{node}",resource="memory"', "100+0x10"),
                ("kube_pod_container_resource_requests", f'node="{node}",resource="cpu"', "1+0x10"),
                ("kube_pod_container_resource_requests", f'node="{node}",resource="memory"', "50+0x10"),
                ("node_uname_info", f'instance="{instance}",nodename="{node}",job="node-exporter"', "1+0x10"),
                ("node_cpu_seconds_total", f'instance="{instance}",mode="idle",job="node-exporter"', "0+45x10"),
                ("node_memory_MemAvailable_bytes", f'instance="{instance}",job="node-exporter"', "25+0x10"),
                ("node_memory_MemTotal_bytes", f'instance="{instance}",job="node-exporter"', "100+0x10"),
                ("node_filesystem_avail_bytes", f'instance="{instance}",mountpoint="/var",job="node-exporter"', "20+0x10"),
                ("node_filesystem_size_bytes", f'instance="{instance}",mountpoint="/var",job="node-exporter"', "100+0x10"),
            ):
                series.append({"series": f"{metric}{{{labels}}}", "values": values})
        series.append({
            "series": 'kube_node_labels{node="talos-control",label_homelab_thecavespace_net_name="control-plane-01"}',
            "values": "1+0x10",
        })
        queries = []
        dashboard = self.dashboards["resources.json"]
        for panel_id, expected in ((1, 25), (2, 75), (3, 25), (4, 50), (8, 80)):
            panel = next(panel for panel in dashboard["panels"] if panel["id"] == panel_id)
            target = panel["targets"][0]
            self.assertIn("{{node_name}}", target["legendFormat"])
            expression = target["expr"].replace("$__rate_interval", "5m")
            queries.append({
                "expr": f"sum by (node_name) ({expression})",
                "eval_time": "10m",
                "exp_samples": [
                    {"labels": f'{{node_name="{name}"}}', "value": expected}
                    for name in ("control-plane-01", "talos-worker")
                ],
            })
        with tempfile.TemporaryDirectory(prefix="node-dashboard-") as directory:
            root = Path(directory)
            (root / "rules.json").write_text(json.dumps({"groups": groups}))
            path = root / "tests.json"
            path.write_text(json.dumps({
                "rule_files": ["rules.json"], "evaluation_interval": "1m",
                "tests": [{"interval": "1m", "input_series": series, "promql_expr_test": queries}],
            }))
            result = subprocess.run(["promtool", "test", "rules", str(path)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            # Existing history predates these recording rules.
            (root / "rules.json").write_text(json.dumps({"groups": []}))
            for query in queries:
                query["exp_samples"][0]["labels"] = '{node_name="talos-control"}'
            path.write_text(json.dumps({
                "rule_files": ["rules.json"], "evaluation_interval": "1m",
                "tests": [{"interval": "1m", "input_series": series, "promql_expr_test": queries}],
            }))
            result = subprocess.run(["promtool", "test", "rules", str(path)],
                                    capture_output=True, text=True, timeout=20)
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

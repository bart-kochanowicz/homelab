import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .support import MonitoringTestCase


class NodeAliasTests(MonitoringTestCase):
    def test_node_label_allowlist_is_rendered_for_kube_state_metrics(self):
        deployment = next(
            item
            for item in self.resources
            if item["kind"] == "Deployment"
            and item["metadata"]["name"] == "kube-prometheus-stack-kube-state-metrics"
        )
        args = deployment["spec"]["template"]["spec"]["containers"][0]["args"]
        self.assertIn(
            "--metric-labels-allowlist=nodes=[homelab.thecavespace.net/name]", args
        )

    def test_node_panels_preserve_values_with_aliases_and_unlabelled_nodes(self):
        groups = next(
            item["spec"]["groups"]
            for item in self.resources
            if item["kind"] == "PrometheusRule"
            and item["metadata"]["name"] == "homelab-security-and-operations"
        )
        series: list[dict[str, str]] = []
        for node, instance in (
            ("talos-control", "10.0.70.11:9100"),
            ("talos-worker", "10.0.70.12:9100"),
        ):
            for metric, labels, values in (
                ("kube_node_info", f'node="{node}"', "1+0x10"),
                (
                    "kube_node_status_allocatable",
                    f'node="{node}",resource="cpu"',
                    "4+0x10",
                ),
                (
                    "kube_node_status_allocatable",
                    f'node="{node}",resource="memory"',
                    "100+0x10",
                ),
                (
                    "kube_pod_container_resource_requests",
                    f'node="{node}",resource="cpu"',
                    "1+0x10",
                ),
                (
                    "kube_pod_container_resource_requests",
                    f'node="{node}",resource="memory"',
                    "50+0x10",
                ),
                (
                    "node_uname_info",
                    f'instance="{instance}",nodename="{node}",job="node-exporter"',
                    "1+0x10",
                ),
                (
                    "node_cpu_seconds_total",
                    f'instance="{instance}",mode="idle",job="node-exporter"',
                    "0+45x10",
                ),
                (
                    "node_memory_MemAvailable_bytes",
                    f'instance="{instance}",job="node-exporter"',
                    "25+0x10",
                ),
                (
                    "node_memory_MemTotal_bytes",
                    f'instance="{instance}",job="node-exporter"',
                    "100+0x10",
                ),
                (
                    "node_filesystem_avail_bytes",
                    f'instance="{instance}",mountpoint="/var",job="node-exporter"',
                    "20+0x10",
                ),
                (
                    "node_filesystem_size_bytes",
                    f'instance="{instance}",mountpoint="/var",job="node-exporter"',
                    "100+0x10",
                ),
            ):
                series.append({"series": f"{metric}{{{labels}}}", "values": values})
        series.append(
            {
                "series": 'kube_node_labels{node="talos-control",label_homelab_thecavespace_net_name="control-plane-01"}',
                "values": "1+0x10",
            }
        )
        queries: list[dict[str, Any]] = []
        dashboard = self.dashboards["resources.json"]
        for panel_id, expected in ((1, 25), (2, 75), (3, 25), (4, 50), (8, 80)):
            panel = next(
                panel for panel in dashboard["panels"] if panel["id"] == panel_id
            )
            target = panel["targets"][0]
            self.assertIn("{{node_name}}", target["legendFormat"])
            expression = target["expr"].replace("$__rate_interval", "5m")
            queries.append(
                {
                    "expr": f"sum by (node_name) ({expression})",
                    "eval_time": "10m",
                    "exp_samples": [
                        {"labels": f'{{node_name="{name}"}}', "value": expected}
                        for name in ("control-plane-01", "talos-worker")
                    ],
                }
            )
        with tempfile.TemporaryDirectory(prefix="node-dashboard-") as directory:
            root = Path(directory)
            (root / "rules.json").write_text(json.dumps({"groups": groups}))
            path = root / "tests.json"
            path.write_text(
                json.dumps(
                    {
                        "rule_files": ["rules.json"],
                        "evaluation_interval": "1m",
                        "tests": [
                            {
                                "interval": "1m",
                                "input_series": series,
                                "promql_expr_test": queries,
                            }
                        ],
                    }
                )
            )
            result = subprocess.run(
                ["promtool", "test", "rules", str(path)],
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            # Existing history predates these recording rules.
            (root / "rules.json").write_text(json.dumps({"groups": []}))
            for query in queries:
                query["exp_samples"][0]["labels"] = '{node_name="talos-control"}'
            path.write_text(
                json.dumps(
                    {
                        "rule_files": ["rules.json"],
                        "evaluation_interval": "1m",
                        "tests": [
                            {
                                "interval": "1m",
                                "input_series": series,
                                "promql_expr_test": queries,
                            }
                        ],
                    }
                )
            )
            result = subprocess.run(
                ["promtool", "test", "rules", str(path)],
                capture_output=True,
                text=True,
                timeout=20,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

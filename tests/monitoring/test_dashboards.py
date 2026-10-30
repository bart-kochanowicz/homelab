import json
import subprocess
import tempfile
from pathlib import Path

from .support import MonitoringTestCase


class DashboardTests(MonitoringTestCase):
    def test_dashboard_files_are_provisioned_without_a_second_copy(self):
        configmap = next(
            item
            for item in self.resources
            if item["kind"] == "ConfigMap"
            and item["metadata"]["name"] == "homelab-dashboards"
        )
        self.assertEqual(configmap["metadata"]["namespace"], "monitoring")
        self.assertEqual(configmap["metadata"]["labels"]["grafana_dashboard"], "1")
        self.assertEqual(
            configmap["metadata"]["annotations"]["grafana_folder"],
            "/tmp/dashboards/Homelab",
        )
        self.assertEqual(set(configmap["data"]), set(self.dashboards))
        for name, dashboard in self.dashboards.items():
            self.assertEqual(json.loads(configmap["data"][name]), dashboard)
        provider = next(
            item
            for item in self.resources
            if item["kind"] == "ConfigMap" and "provider.yaml" in item.get("data", {})
        )
        self.assertIn(
            "foldersFromFilesStructure: true", provider["data"]["provider.yaml"]
        )
        self.assertIn("allowUiUpdates: false", provider["data"]["provider.yaml"])
        grafana = next(
            item
            for item in self.resources
            if item["kind"] == "Deployment"
            and item["metadata"]["name"] == "kube-prometheus-stack-grafana"
        )
        sidecar = next(
            item
            for item in grafana["spec"]["template"]["spec"]["containers"]
            if item["name"] == "grafana-sc-dashboard"
        )
        env = {entry["name"]: entry.get("value") for entry in sidecar["env"]}
        self.assertEqual(env["FOLDER_ANNOTATION"], "grafana_folder")

    def test_uids_and_datasources_match_the_provisioned_instance(self):
        uids = [dashboard["uid"] for dashboard in self.dashboards.values()]
        self.assertEqual(len(uids), len(set(uids)))
        other_uids: set[str | None] = set()
        for resource in self.resources:
            if (
                resource["kind"] != "ConfigMap"
                or resource["metadata"]["name"] == "homelab-dashboards"
            ):
                continue
            for name, content in resource.get("data", {}).items():
                if name.endswith(".json"):
                    other_uids.add(json.loads(content).get("uid"))
        self.assertFalse(
            set(uids) & other_uids, "A dashboard would overwrite an existing UID"
        )
        for dashboard in self.dashboards.values():
            self.assertNotIn("__inputs", dashboard)
            self.assertFalse(dashboard["editable"])
            ids = [panel["id"] for panel in dashboard["panels"]]
            self.assertEqual(len(ids), len(set(ids)))
            for panel in dashboard["panels"]:
                self.assertEqual(
                    panel["datasource"], {"type": "prometheus", "uid": "prometheus"}
                )
                for link in dashboard["links"]:
                    if link["url"].startswith("/d/"):
                        self.assertIn(link["url"][3:], uids)

    def test_all_dashboard_queries_are_valid_promql(self):
        rules: list[dict[str, str]] = []
        for dashboard in self.dashboards.values():
            for panel in dashboard["panels"]:
                for target in panel["targets"]:
                    expression = (
                        target["expr"]
                        .replace("$__rate_interval", "5m")
                        .replace("$namespace", ".*")
                    )
                    self.assertNotIn("$", expression.replace("$1", ""))
                    rules.append(
                        {"record": f"dashboard_query_{len(rules)}", "expr": expression}
                    )
        with tempfile.TemporaryDirectory(prefix="dashboard-promql-") as directory:
            path = Path(directory) / "rules.json"
            path.write_text(
                json.dumps({"groups": [{"name": "dashboards", "rules": rules}]})
            )
            result = subprocess.run(
                ["promtool", "check", "rules", str(path)],
                capture_output=True,
                text=True,
                timeout=15,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

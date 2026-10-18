import json
from pathlib import Path
import subprocess
import unittest
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]


class EnvironmentPrivacyTests(unittest.TestCase):
    def yaml(self, expression, *paths):
        result = subprocess.run(
            ["yq", "-o=json", "-I=0", expression, *(str(path) for path in paths)],
            capture_output=True, text=True, check=True, timeout=30,
        )
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def assert_example_domain(self, hostname):
        self.assertTrue(any(
            hostname == domain or hostname.endswith("." + domain)
            for domain in ("example.com", "example.net", "example.org")
        ), "Public endpoint values must use reserved example domains")

    def test_public_endpoint_defaults_are_reserved_examples(self):
        deployment, = self.yaml(".", ROOT / "apps/n8n/deployment.yaml")
        environment = {
            item["name"]: item.get("value")
            for item in deployment["spec"]["template"]["spec"]["containers"][0]["env"]
        }
        self.assert_example_domain(environment["N8N_HOST"])
        for name in ("N8N_EDITOR_BASE_URL", "WEBHOOK_URL"):
            self.assert_example_domain(urlparse(environment[name]).hostname)

        config = ROOT / "system/argocd/argocd-cm.yaml"
        data, = self.yaml(".data", config)
        self.assert_example_domain(urlparse(data["url"]).hostname)
        dex, = self.yaml('.data."dex.config" | from_yaml', config)
        for connector in dex["connectors"]:
            self.assert_example_domain(urlparse(connector["config"]["redirectURI"]).hostname)

    def test_public_certificates_do_not_disclose_environment_domains(self):
        resources = self.yaml(
            'select(.kind == "Certificate" or .kind == "ClusterIssuer")',
            *sorted((ROOT / ".cache/rendered").glob("*.yaml")),
        )
        self.assertTrue(resources, "Render manifests before checking certificate privacy")
        for resource in resources:
            if resource["kind"] == "ClusterIssuer":
                for solver in resource["spec"].get("acme", {}).get("solvers", []):
                    for zone in solver.get("selector", {}).get("dnsZones", []):
                        self.assert_example_domain(zone)
                continue
            namespace = resource["metadata"]["namespace"]
            for name in resource["spec"].get("dnsNames", []):
                if "." not in name or any(name.endswith(suffix) for suffix in (
                    f".{namespace}", f".{namespace}.svc", f".{namespace}.svc.cluster.local",
                )):
                    continue
                self.assert_example_domain(name.removeprefix("*."))


if __name__ == "__main__":
    unittest.main()

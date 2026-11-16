import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class VaultFoundationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rendered = subprocess.run(
            [
                "helm",
                "template",
                "vault",
                "system/vault",
                "--namespace",
                "vault",
                "--skip-tests",
                "--kube-version",
                "1.34.0",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        cls.resources = [item for item in yaml.safe_load_all(rendered) if item]

    def test_server_preserves_storage_and_starts_sealed(self):
        servers = [r for r in self.resources if r["kind"] == "StatefulSet"]
        self.assertEqual(len(servers), 1)
        server = servers[0]
        self.assertEqual(server["spec"]["replicas"], 1)
        self.assertEqual(
            server["spec"]["persistentVolumeClaimRetentionPolicy"],
            {"whenDeleted": "Retain", "whenScaled": "Retain"},
        )
        claims = server["spec"]["volumeClaimTemplates"]
        self.assertEqual(
            {claim["metadata"]["name"] for claim in claims}, {"data", "audit"}
        )
        for claim in claims:
            self.assertEqual(claim["spec"]["storageClassName"], "local-path-nvme")
        pod = server["spec"]["template"]["spec"]
        container = pod["containers"][0]
        self.assertNotIn("livenessProbe", container)
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertIn(
            "/tmp", {mount["mountPath"] for mount in container["volumeMounts"]}
        )
        self.assertFalse(
            any("VAULT_DEV_ROOT_TOKEN_ID" == e["name"] for e in container["env"])
        )

    def test_raft_and_listener_use_tls(self):
        config = next(
            r["data"]["extraconfig-from-values.hcl"]
            for r in self.resources
            if r["kind"] == "ConfigMap"
            and "extraconfig-from-values.hcl" in r.get("data", {})
        )
        self.assertIn('storage "raft"', config)
        self.assertIn('tls_cert_file = "/vault/userconfig/vault-tls/tls.crt"', config)
        self.assertIn('tls_reload_interval = "30s"', config)
        self.assertNotIn("tls_disable", config)
        self.assertFalse(any(r["kind"] == "Secret" for r in self.resources))


if __name__ == "__main__":
    unittest.main()

import base64
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


CONFIG = Path(__file__).resolve().parents[1] / ".gitleaks.toml"
SEALED_SECRET_PATHS = (
    "apps/n8n/sealed-secret.yaml",
    "system/cloudflared/sealed-cloudflared-token.yaml",
    "system/cert-manager-ca/sealed-root-ca.yaml",
    "system/cert-manager-acme/sealed-cloudflare-token.yaml",
    "system/argocd/argocd-sso-sealed-secret.yaml",
    "system/argocd/homelab-config-repository.yaml",
    "system/monitoring/grafana-admin-sealed-secret.yaml",
    "system/monitoring/alertmanager-email-sealed-secret.yaml",
)


class SecretScanningTests(unittest.TestCase):
    def scan(self, path, content, default_config=False):
        cache = CONFIG.parent / ".cache"
        cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="secret-scanning-", dir=cache) as directory:
            root = Path(directory) / "tree"
            fixture = root / path
            fixture.parent.mkdir(parents=True)
            fixture.write_text(content)
            report = Path(directory) / "findings.json"
            config = CONFIG
            if default_config:
                config = Path(directory) / "default.toml"
                config.write_text("[extend]\nuseDefault = true\n")
            result = subprocess.run(
                ["gitleaks", "dir", "--config", str(config), "--redact", "--no-banner",
                 "--exit-code", "10", "--report-format", "json", "--report-path", str(report), "."],
                cwd=root, capture_output=True, text=True, timeout=20,
            )
            self.assertIn(result.returncode, (0, 10), result.stderr)
            self.assertTrue(report.is_file(), f"Gitleaks did not produce a report: {result.stderr}")
            findings = json.loads(report.read_text())
            self.assertEqual(result.returncode, 10 if findings else 0, result.stderr)
            return findings

    def test_plaintext_tokens_are_detected_in_sealed_secret_files(self):
        token = "ghp_" + base64.b64encode(
            hashlib.sha256(b"non-working-regression-token").digest()
        ).decode().replace("+", "A").replace("/", "B")[:36]
        for path in SEALED_SECRET_PATHS:
            for location, content in {
                "comment": f"# GitHub token: {token}\n",
                "template": f"spec:\n  template:\n    data:\n      github-token: {token}\n",
                "stringData": f"stringData:\n  github-token: {token}\n",
            }.items():
                with self.subTest(path=path, location=location):
                    findings = self.scan(path, content)
                    self.assertTrue(any(finding["RuleID"] == "github-pat" for finding in findings))

    def test_ciphertext_allowlist_requires_both_content_and_path(self):
        ciphertext = base64.b64encode(
            b"\x02\x00" + hashlib.shake_256(b"synthetic-sealed-secret").digest(600)
        ).decode()
        content = f"spec:\n  encryptedData:\n    api_key: {ciphertext}\n"
        self.assertTrue(self.scan(SEALED_SECRET_PATHS[0], content, default_config=True))
        for path in SEALED_SECRET_PATHS:
            with self.subTest(path=path):
                self.assertEqual(self.scan(path, content), [])
                plaintext = base64.b64encode(hashlib.sha256(b"non-working-api-key").digest()).decode()
                findings = self.scan(path, content + f"# api_key: {plaintext}\n")
                self.assertTrue(any(finding["RuleID"] == "generic-api-key" for finding in findings))
        self.assertTrue(self.scan("apps/unsealed-secret.yaml", content))


if __name__ == "__main__":
    unittest.main()

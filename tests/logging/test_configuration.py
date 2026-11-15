import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class LoggingConfigurationTests(unittest.TestCase):
    def test_backup_freshness_tracks_the_managed_server_name(self):
        server_config = (ROOT / "terraform/crafty/servers.tf").read_text()
        server = re.search(
            r'resource "crafty_minecraft_server" "atm10_8_3"\s*\{\s*name\s*=\s*"([^"]+)"',
            server_config,
        )
        self.assertIsNotNone(server, "Expected a literal name for the active server")
        assert server is not None
        rules = yaml.safe_load(
            (ROOT / "system/logging/minecraft-rules.yaml").read_text()
        )["groups"][0]["rules"]
        expression = next(
            rule["expr"]
            for rule in rules
            if rule["alert"] == "MinecraftBackupUnhealthy"
        )
        self.assertIn(
            f'server_name="{server.group(1)}",backup_status="success"', expression
        )
        self.assertEqual(
            re.findall(r'server_name="([^"]+)"', expression), [server.group(1)] * 5
        )

    def test_logging_syncs_changes_without_pruning(self):
        application = yaml.safe_load((ROOT / "system/argocd/logging.yaml").read_text())
        automated = application["spec"]["syncPolicy"]["automated"]
        self.assertTrue(automated["selfHeal"])
        self.assertFalse(automated.get("prune", False))

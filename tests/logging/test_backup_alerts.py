import time
from datetime import timedelta

import yaml

from .support import LOGGING, LoggingTestCase


class BackupAlertTests(LoggingTestCase):
    def test_weekly_copy_does_not_alert_between_runs(self):
        server = "weekly-healthy"
        self.push(server, [("success", timedelta(days=7))])
        self.assertFalse(self.unhealthy(server))

    def test_failed_copy_alerts_without_any_prior_success(self):
        server = "first-attempt-failed"
        self.push(server, [("failure", timedelta(minutes=1))])
        self.assertTrue(self.unhealthy(server))

    def test_startup_failure_is_a_recent_event_alert(self):
        rules = yaml.safe_load((LOGGING / "minecraft-rules.yaml").read_text())[
            "groups"
        ][0]["rules"]
        expression = next(
            rule["expr"] for rule in rules if rule["alert"] == "CraftyBackupStartFailed"
        )
        self.push(
            "startup-failure",
            [("event", timedelta(minutes=1))],
            "app.classes.shared.server - Failed to start backup: fixture",
        )
        self.assertTrue(self.query(expression))
        self.assertFalse(
            self.query(expression, time.time_ns() + 16 * 60 * 1_000_000_000)
        )

    def test_new_success_clears_failure_and_later_failure_reopens_it(self):
        server = "backup-retry"
        self.push(server, [("failure", timedelta(minutes=3))])
        self.assertTrue(self.unhealthy(server))
        self.push(server, [("success", timedelta(minutes=2))])
        self.assertFalse(self.unhealthy(server))
        self.push(server, [("failure", timedelta(minutes=1))])
        self.assertTrue(self.unhealthy(server))

    def test_missing_copy_cannot_be_hidden_by_another_server(self):
        self.push("another-server", [("success", timedelta(minutes=1))])
        self.assertTrue(self.unhealthy("never-copied"))
        self.push("stale-copy", [("success", timedelta(days=9))])
        self.assertTrue(self.unhealthy("stale-copy"))

    def test_absent_history_stays_unhealthy_after_failure_retention_expires(self):
        server = "expired-failure-history"
        self.push(server, [("failure", timedelta(minutes=1))])
        self.assertTrue(self.unhealthy(server))
        self.assertTrue(
            self.unhealthy(server, time.time_ns() + 15 * 86400 * 1_000_000_000)
        )

    def test_loki_restart_preserves_success_history(self):
        server = "persisted-success"
        self.push(server, [("success", timedelta(minutes=1))])
        self.assertFalse(self.unhealthy(server))
        self.command("docker", "restart", self.name)
        self.wait_ready()
        self.assertFalse(self.unhealthy(server))

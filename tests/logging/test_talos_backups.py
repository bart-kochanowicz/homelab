import json
import time
from datetime import timedelta
from urllib.request import Request, urlopen

import yaml

from .support import LOGGING, LoggingTestCase


class TalosBackupAlertTests(LoggingTestCase):
    talos_rules: dict[str, str]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        rules = yaml.safe_load((LOGGING / "talos-backup-rules.yaml").read_text())[
            "groups"
        ][0]["rules"]
        cls.talos_rules = {rule["alert"]: rule["expr"] for rule in rules}

    def journal(self, node: str, events: list[tuple[str, timedelta]]) -> None:
        streams = [
            {
                "stream": {
                    "node": node,
                    "source": "journal",
                    "service_name": "talos-etcd-backup.service",
                },
                "values": [
                    [
                        str(time.time_ns() - int(age.total_seconds() * 1e9)),
                        message,
                    ]
                    for message, age in events
                ],
            }
        ]
        request = Request(
            self.url + "/loki/api/v1/push",
            data=json.dumps({"streams": streams}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=10) as response:
            self.assertEqual(response.status, 204)

    def alert(
        self,
        node: str,
        name: str = "TalosEtcdBackupUnhealthy",
        at: float | None = None,
    ) -> bool:
        return bool(self.query(self.talos_rules[name].replace("houston-01", node), at))

    def test_weekly_success_is_healthy_until_the_eight_day_limit(self):
        node = "weekly-talos"
        self.journal(node, [("TALOS_ETCD_BACKUP_SUCCESS", timedelta(days=7, hours=23))])
        self.assertFalse(self.alert(node))
        self.assertTrue(self.alert(node, at=time.time_ns() + 2 * 3600 * 1_000_000_000))

    def test_failure_timeout_and_retry_follow_the_latest_verified_outcome(self):
        node = "retry-talos"
        self.journal(
            node,
            [("TALOS_ETCD_BACKUP_RESULT=exit-code", timedelta(minutes=4))],
        )
        self.assertTrue(self.alert(node))
        self.journal(node, [("TALOS_ETCD_BACKUP_SUCCESS", timedelta(minutes=3))])
        self.assertFalse(self.alert(node))
        self.journal(node, [("TALOS_ETCD_BACKUP_RESULT=timeout", timedelta(minutes=2))])
        self.assertTrue(self.alert(node))
        self.journal(node, [("TALOS_ETCD_BACKUP_SUCCESS", timedelta(minutes=1))])
        self.assertFalse(self.alert(node))

    def test_clean_manager_result_cannot_replace_a_verified_backup(self):
        self.journal(
            "canceled-talos",
            [("TALOS_ETCD_BACKUP_RESULT=success", timedelta(minutes=1))],
        )
        self.assertTrue(self.alert("canceled-talos"))

    def test_another_host_cannot_hide_missing_or_expired_history(self):
        self.journal(
            "other-talos", [("TALOS_ETCD_BACKUP_SUCCESS", timedelta(minutes=1))]
        )
        self.assertTrue(self.alert("missing-talos"))
        self.journal(
            "expired-talos", [("TALOS_ETCD_BACKUP_SUCCESS", timedelta(days=9))]
        )
        self.assertTrue(self.alert("expired-talos"))
        self.assertTrue(
            self.alert("expired-talos", at=time.time_ns() + 15 * 86400 * 1_000_000_000)
        )

    def test_client_expiry_warning_clears_after_warning_history_expires(self):
        node = "expiring-talos"
        name = "TalosBackupClientExpiring"
        self.assertFalse(self.alert(node, name))
        self.journal(
            node,
            [("TALOS_ETCD_BACKUP_CLIENT_EXPIRING", timedelta(minutes=1))],
        )
        self.assertTrue(self.alert(node, name))
        self.assertTrue(
            self.alert(node, name, time.time_ns() + 7 * 86400 * 1_000_000_000)
        )
        self.assertFalse(
            self.alert(node, name, time.time_ns() + 9 * 86400 * 1_000_000_000)
        )

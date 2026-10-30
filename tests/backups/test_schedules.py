import json

from .support import DATABASES, PvcBackupTestCase


class PvcScheduleTests(PvcBackupTestCase):
    def test_schedules_select_only_prepared_backups_and_require_private_authenticated_tls(
        self,
    ):
        schedules = {
            item["metadata"]["namespace"]: item
            for item in self.resources
            if item["kind"] == "Schedule"
        }
        self.assertEqual(set(schedules), set(DATABASES))
        for namespace, schedule in schedules.items():
            with self.subTest(namespace=namespace):
                spec = schedule["spec"]
                selectors = spec["backup"]["labelSelectors"]
                labels = self.prebackups[namespace]["metadata"]["labels"]
                self.assertTrue(selectors)
                self.assertTrue(
                    any(
                        selector.get("matchLabels")
                        and all(
                            labels.get(key) == value
                            for key, value in selector["matchLabels"].items()
                        )
                        for selector in selectors
                    )
                )
                self.assertTrue(
                    spec["backend"]["rest"]["url"].startswith(
                        "https://10.0.70.10:8444/"
                    )
                )
                self.assertTrue(spec["backend"]["rest"]["userSecretRef"])
                self.assertTrue(spec["backend"]["rest"]["passwordSecretReg"])
                self.assertTrue(spec["backend"]["repoPasswordSecretRef"])
                self.assertTrue(spec["backend"]["tlsOptions"]["caCert"].startswith("/"))
                self.assertNotIn("KUBECONFIG", json.dumps(spec))
        self.assertFalse(
            any(
                item["kind"]
                in {"Role", "RoleBinding", "Lease", "PersistentVolumeClaim"}
                for item in self.resources
            )
        )

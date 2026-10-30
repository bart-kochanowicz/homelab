import json
import os
import subprocess
import tarfile

from .support import DATABASES, PvcBackupTestCase


class PvcRestoreTests(PvcBackupTestCase):
    def test_readonly_wal_backups_restore_databases_and_nested_configuration_through_restic(
        self,
    ):
        password = self.root / "password"
        password.write_text("isolated-test-repository\n")
        password.chmod(0o600)
        environment = os.environ | {
            "RESTIC_REPOSITORY": str(self.root / "repository"),
            "RESTIC_PASSWORD_FILE": str(password),
            "RESTIC_CACHE_DIR": str(self.root / "cache"),
            "GOMAXPROCS": "2",
        }
        subprocess.run(
            ["restic", "init"],
            env=environment,
            capture_output=True,
            check=True,
            timeout=30,
        )
        for namespace in DATABASES:
            with self.subTest(namespace=namespace):
                source, staging = self.source(namespace)
                self.open_wal(namespace, source)
                originals = {
                    path: path.read_bytes()
                    for path in source.rglob("*")
                    if path.is_file() and not path.name.endswith("-shm")
                }
                for path in source.rglob("*"):
                    path.chmod(0o555 if path.is_dir() else 0o444)
                source.chmod(0o555)
                try:
                    prepared = self.prepare(namespace, source, staging)
                finally:
                    source.chmod(0o700)
                    for path in source.rglob("*"):
                        path.chmod(0o700 if path.is_dir() else 0o600)
                self.assertEqual(
                    prepared.returncode, 0, prepared.stdout + prepared.stderr
                )
                for path, contents in originals.items():
                    self.assertEqual(
                        path.read_bytes(), contents, "Source data must remain unchanged"
                    )
                archive = self.archive_path(namespace, staging)
                with archive.open("rb") as stream:
                    result = subprocess.run(
                        [
                            "restic",
                            "backup",
                            "--json",
                            "--stdin",
                            "--stdin-filename",
                            f"/{namespace}.tar",
                        ],
                        env=environment,
                        stdin=stream,
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=30,
                    )
                snapshot = next(
                    json.loads(line)["snapshot_id"]
                    for line in result.stdout.splitlines()
                    if json.loads(line).get("message_type") == "summary"
                )
                restored_tar = self.root / f"{namespace}.tar"
                with restored_tar.open("wb") as stream:
                    subprocess.run(
                        ["restic", "dump", snapshot, f"/{namespace}.tar"],
                        env=environment,
                        stdout=stream,
                        stderr=subprocess.PIPE,
                        check=True,
                        timeout=30,
                    )
                restored = self.root / namespace / "restored"
                restored.mkdir()
                with tarfile.open(restored_tar) as bundle:
                    bundle.extractall(restored, filter="data")
                with tarfile.open(restored / "files.tar") as files:
                    files.extractall(restored, filter="data")
                self.assert_database(namespace, restored)
                self.assertEqual(
                    (restored / "config.yaml").read_text(),
                    "fixture: application configuration\n",
                )
                self.assertEqual(
                    (restored / ".storage/settings.json").read_text(),
                    '{"fixture": "nested configuration"}\n',
                )

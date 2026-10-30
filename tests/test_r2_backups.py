"""Exercise backup failure handling and retention evidence without live R2 access."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class R2BackupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="homelab-r2-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.staging = self.root / "backup-staging"
        self.staging.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = dict(
            os.environ,
            PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
            TEST_ROOT=str(self.root),
            R2_ACCOUNT_ID="a" * 32,
            R2_ACCESS_KEY_ID="b" * 32,
            R2_SECRET_ACCESS_KEY="c" * 64,
            AWS_ACCESS_KEY_ID="garage-access",
            AWS_SECRET_ACCESS_KEY="garage-secret",
            AWS_SESSION_TOKEN="garage-session",
            AWS_SECURITY_TOKEN="garage-security",
            AWS_PROFILE="garage",
            AWS_DEFAULT_PROFILE="garage",
            AWS_MAX_ATTEMPTS="9",
        )
        for name, body in {
            "mountpoint": "exit 0",
            "sleep": "exit 0",
            "timeout": 'shift; exec "$@"',
            "terraform": """
                [[ $AWS_ACCESS_KEY_ID == garage-access && $AWS_SECRET_ACCESS_KEY == garage-secret ]]
                printf '%s\\n' '{"version":4,"serial":1,"lineage":"test","resources":[]}'
            """,
        }.items():
            self.executable(
                name, "#!/usr/bin/env bash\nset -eu\n" + textwrap.dedent(body)
            )
        self.executable(
            "aws",
            f"#!{sys.executable}\n"
            + textwrap.dedent("""\
            import json, os, sys
            from pathlib import Path
            assert os.environ["AWS_ACCESS_KEY_ID"] == "b" * 32
            assert os.environ["AWS_SECRET_ACCESS_KEY"] == "c" * 64
            assert not any(name in os.environ for name in (
                "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN", "AWS_PROFILE", "AWS_DEFAULT_PROFILE"))
            assert os.environ["AWS_MAX_ATTEMPTS"] == "1"
            assert os.environ["AWS_RETRY_MODE"] == "standard"
            assert os.environ["AWS_CONFIG_FILE"] == os.environ["AWS_SHARED_CREDENTIALS_FILE"] == "/dev/null"
            assert os.environ["AWS_REQUEST_CHECKSUM_CALCULATION"] == "when_required"
            args = sys.argv[1:]
            assert args[args.index("--endpoint-url") + 1] == "https://" + "a" * 32 + ".r2.cloudflarestorage.com"
            assert args[args.index("--region") + 1] == "auto"
            operation = args[args.index("s3api") + 1]
            key = args[args.index("--key") + 1]
            assert args[args.index("--bucket") + 1] == "houston-terraform-state-backups"
            root = Path(os.environ["TEST_ROOT"])
            target = root / "objects" / key
            with (root / "requests").open("a") as log:
                log.write(json.dumps([operation, key]) + "\\n")
            def error(code):
                print(f"An error occurred ({code}) when calling the operation: test failure", file=sys.stderr)
                sys.exit(254)
            if operation == "put-object":
                if not target.exists():
                    assert "--if-none-match" in args, "New objects require conditional creation"
                if "--if-none-match" in args:
                    assert args[args.index("--if-none-match") + 1] == "*"
                    if target.exists():
                        error("PreconditionFailed")
                elif key.startswith("backups/") and target.exists() and os.environ.get("LOCK_CODE") != "allow":
                    error(os.environ.get("LOCK_CODE", "ObjectLockedByBucketPolicy"))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(Path(args[args.index("--body") + 1]).read_bytes())
                if os.environ.get("AMBIGUOUS_PUT"):
                    error("InternalError")
            elif operation == "get-object":
                if not target.exists():
                    error("NoSuchKey")
                destination = args[args.index("--key") + 2]
                Path(destination).write_bytes(b"corrupt" if os.environ.get("CORRUPT_READ") else target.read_bytes())
            elif operation == "delete-object":
                if key.startswith("backups/") and os.environ.get("LOCK_CODE") != "allow":
                    error(os.environ.get("LOCK_CODE", "ObjectLockedByBucketPolicy"))
                target.unlink()
            else:
                raise AssertionError(operation)
        """),
        )

    def executable(self, name: str, content: str) -> None:
        path = self.bin / name
        path.write_text(content)
        path.chmod(0o700)

    def run_script(
        self, name: str, *args: str, **env: str
    ) -> subprocess.CompletedProcess[str]:
        script = (SCRIPTS / name).read_text().replace("/srv/terraform", str(self.root))
        script = script.replace("/usr/local/bin/terraform", str(self.bin / "terraform"))
        return subprocess.run(
            ["bash", "-c", script, name, *args],
            env=self.env | env,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_backup_reads_back_before_cleanup(self):
        result = self.run_script(
            "backup-terraform-state.sh", str(self.root), "checks/garage-backend"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Verified R2 backup:", result.stdout)
        self.assertEqual(list(self.staging.iterdir()), [])
        requests = [
            json.loads(line)
            for line in (self.root / "requests").read_text().splitlines()
        ]
        self.assertEqual([item[0] for item in requests], ["put-object", "get-object"])
        self.assertEqual(requests[0][1], requests[1][1])

    def test_mismatched_readback_retains_snapshot(self):
        result = self.run_script(
            "backup-terraform-state.sh",
            str(self.root),
            "checks/garage-backend",
            CORRUPT_READ="1",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("R2 readback differs", result.stderr)
        self.assertEqual(len(list(self.staging.glob("*/snapshot.tfstate"))), 1)

    def test_ambiguous_upload_is_not_retried_and_retains_snapshot(self):
        result = self.run_script(
            "backup-terraform-state.sh",
            str(self.root),
            "checks/garage-backend",
            AMBIGUOUS_PUT="1",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len((self.root / "requests").read_text().splitlines()), 1)
        self.assertEqual(len(list(self.staging.glob("*/snapshot.tfstate"))), 1)

    def test_retention_requires_bucket_lock_evidence(self):
        for code, succeeds in (
            ("ObjectLockedByBucketPolicy", True),
            ("AccessDenied", False),
            ("allow", False),
        ):
            with self.subTest(code=code):
                result = self.run_script("check-r2-retention.sh", LOCK_CODE=code)
                self.assertEqual(result.returncode == 0, succeeds, result.stderr)
                self.assertEqual("Retention verified:" in result.stdout, succeeds)

    def test_restore_rejects_changed_bytes_before_running_terraform(self):
        key = "backups/checks/garage-backend/2026-10-30T00-00-00Z-abcd.tfstate"
        snapshot = self.root / "objects" / key
        snapshot.parent.mkdir(parents=True)
        snapshot.write_bytes(b"original")
        result = self.run_script(
            "check-terraform-state-restore.sh",
            key,
            hashlib.sha256(b"original").hexdigest(),
            CORRUPT_READ="1",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Snapshot SHA256 does not match", result.stderr)
        self.assertEqual(len(list(self.staging.glob("*/snapshot.tfstate"))), 1)
        self.assertFalse(list(self.staging.glob("*/module")))


if __name__ == "__main__":
    unittest.main()

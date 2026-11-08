"""Exercise download recovery and fail-closed validation without network access."""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class DownloadTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="homelab-download-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name, body in {
            "helm": """
                import os, sys
                from pathlib import Path
                counter = Path("attempts")
                attempt = int(counter.read_text()) + 1 if counter.exists() else 1
                counter.write_text(str(attempt))
                failed = attempt <= int(os.environ["TEST_DOWNLOAD_FAILURES"])
                print("partial" if failed else "complete")
                sys.exit(1 if failed else 0)
            """,
            "yq": """
                from pathlib import Path
                assert Path(".cache/backup-crds.yaml").read_text() == "complete\\n"
            """,
            "kubeconform": """
                from pathlib import Path
                Path("schema-checked").touch()
            """,
        }.items():
            executable = self.bin / name
            executable.write_text(f"#!{sys.executable}\n" + textwrap.dedent(body))
            executable.chmod(0o755)
        sleep = self.bin / "sleep"
        sleep.write_text("#!/bin/sh\nexit 0\n")
        sleep.chmod(0o755)

    def validate(self, failures: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "make",
                "--no-print-directory",
                "-f",
                str(ROOT / "Makefile"),
                "-o",
                "validate-kustomize",
                "validate-backups",
            ],
            cwd=self.root,
            env=os.environ
            | {
                "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                "TEST_DOWNLOAD_FAILURES": str(failures),
            },
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_transient_download_replaces_partial_output_before_schema_validation(self):
        result = self.validate(failures=2)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / "attempts").read_text(), "3")
        self.assertEqual(
            (self.root / ".cache/backup-crds.yaml").read_text(), "complete\n"
        )
        self.assertTrue((self.root / "schema-checked").exists())

    def test_permanent_download_failure_stops_before_schema_validation(self):
        result = self.validate(failures=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / "attempts").read_text(), "3")
        self.assertFalse((self.root / "schema-checked").exists())

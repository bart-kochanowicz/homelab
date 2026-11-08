"""Check that parallel test execution preserves discovery and failure reporting."""

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ParallelTestTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="homelab-ci-tests-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        shutil.copyfile(ROOT / "Makefile", self.root / "Makefile")
        self.modules = {
            "tests.a.test_failure",
            "tests.b.test_second",
            "tests.c.nested.test_third",
            "tests.d.test_fourth",
            "tests.e.test_fifth",
            "tests.test_root",
        }
        for module in self.modules:
            path = self.root / (module.replace(".", "/") + ".py")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        (self.root / "tests/b/support.py").touch()
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        uv = bin_dir / "uv"
        uv.write_text(
            f"#!{sys.executable}\n"
            + textwrap.dedent("""\
                import os, sys
                from pathlib import Path
                module = sys.argv[-2]
                with Path("executed").open("a") as log:
                    log.write(module + "\\n")
                sys.exit(42 if module == os.environ.get("TEST_FAIL_MODULE") else 0)
                """)
        )
        uv.chmod(0o755)
        self.environment = os.environ | {
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]
        }

    def run_suite(self, failing_module: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "make",
                "--no-print-directory",
                "-o",
                "validate-gateway-api",
                "-o",
                "validate-metallb",
                "-o",
                "validate-envoy-gateway",
                "validate-workflows",
            ],
            cwd=self.root,
            env=self.environment | {"TEST_FAIL_MODULE": failing_module},
            capture_output=True,
            text=True,
            timeout=15,
        )

    def assert_all_modules_executed_once(self):
        executed = (self.root / "executed").read_text().splitlines()
        self.assertEqual(set(executed), self.modules)
        self.assertEqual(len(executed), len(self.modules))

    def test_all_modules_including_nested_and_root_tests_are_executed(self):
        result = self.run_suite()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_all_modules_executed_once()

    def test_a_failure_blocks_validation_without_skipping_other_modules(self):
        result = self.run_suite("tests.a.test_failure")
        self.assertNotEqual(result.returncode, 0)
        self.assert_all_modules_executed_once()

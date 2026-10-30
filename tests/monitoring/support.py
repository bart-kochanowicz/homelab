import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONITORING = ROOT / "system/monitoring"


class MonitoringTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dashboards = {
            path.name: json.loads(path.read_text())
            for path in (MONITORING / "dashboards").glob("*.json")
        }
        result = subprocess.run(
            [
                "yq",
                "-o=json",
                "-I=0",
                "select(.kind != null)",
                str(ROOT / ".cache/rendered/system-monitoring.yaml"),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        cls.resources = [
            json.loads(line) for line in result.stdout.splitlines() if line.strip()
        ]

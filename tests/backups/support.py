import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATABASES = {
    "home-assistant": "home-assistant_v2.db",
    "n8n": "database.sqlite",
    "monitoring": "grafana.db",
    "crafty-controller": "db/crafty.sqlite",
}


class PvcBackupTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for tool in ("sqlite3", "restic", "tar", "yq", "helm"):
            if not shutil.which(tool):
                raise RuntimeError(f"Install {tool} before running backup tests")
        rendered = subprocess.run(
            ["helm", "template", "backups", str(ROOT / "system/backups")],
            capture_output=True,
            text=True,
            check=True,
        )
        parsed = subprocess.run(
            ["yq", "-o=json", "-I=0", "select(.kind != null)"],
            input=rendered.stdout,
            capture_output=True,
            text=True,
            check=True,
        )
        cls.resources = [
            json.loads(line) for line in parsed.stdout.splitlines() if line.strip()
        ]
        cls.prebackups = {
            item["metadata"]["namespace"]: item
            for item in cls.resources
            if item["kind"] == "PreBackupPod"
        }

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="homelab-backup-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def prepare(
        self, namespace: str, source: Path, staging: Path
    ) -> subprocess.CompletedProcess[str]:
        init = self.prebackups[namespace]["spec"]["pod"]["spec"]["initContainers"][0]
        paths = {"data": str(source), "staging": str(staging)}
        command = re.sub(
            r"(?<![\w/])/(data|staging)(?=/|\s|$)",
            lambda match: paths[match[1]],
            init["args"][0],
        )
        return subprocess.run(
            ["sh", "-ec", command],
            env=os.environ | {"COPYFILE_DISABLE": "1"},
            capture_output=True,
            text=True,
            timeout=30,
        )

    def archive_path(self, namespace: str, staging: Path) -> Path:
        command = shlex.split(self.prebackups[namespace]["spec"]["backupCommand"])
        self.assertEqual(command[0], "cat")
        self.assertEqual(len(command), 2)
        return Path(command[1].replace("/staging", str(staging)))

    def source(self, namespace: str) -> tuple[Path, Path]:
        source, staging = (
            self.root / namespace / "source",
            self.root / namespace / "staging",
        )
        source.mkdir(parents=True)
        staging.mkdir()
        (source / DATABASES[namespace]).parent.mkdir(parents=True, exist_ok=True)
        (source / ".storage").mkdir()
        (source / ".storage/settings.json").write_text(
            '{"fixture": "nested configuration"}\n'
        )
        (source / "config.yaml").write_text("fixture: application configuration\n")
        return source, staging

    def open_wal(self, namespace: str, source: Path) -> sqlite3.Connection:
        database = sqlite3.connect(source / DATABASES[namespace])
        self.addCleanup(database.close)
        database.execute("PRAGMA journal_mode=WAL")
        database.execute("PRAGMA wal_autocheckpoint=0")
        database.execute("CREATE TABLE settings (value TEXT)")
        database.execute("INSERT INTO settings VALUES ('committed WAL data')")
        database.commit()
        self.assertGreater((source / (DATABASES[namespace] + "-wal")).stat().st_size, 0)
        return database

    def assert_database(self, namespace: str, directory: Path) -> None:
        with closing(sqlite3.connect(directory / DATABASES[namespace])) as database:
            self.assertEqual(
                database.execute("PRAGMA integrity_check").fetchone(), ("ok",)
            )
            self.assertEqual(
                database.execute("SELECT value FROM settings").fetchall(),
                [("committed WAL data",)],
            )

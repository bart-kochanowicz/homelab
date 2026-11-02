import base64
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKUP = ROOT / "infra/ansible/roles/talos_backup/files/backup.yml"


class TalosBackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.restic = shutil.which("restic")
        if not cls.restic:
            raise RuntimeError("Install restic before running Talos backup tests")
        cls.certificates = tempfile.TemporaryDirectory(prefix="talos-client-fixture-")
        cls.addClassCleanup(cls.certificates.cleanup)
        cert = Path(cls.certificates.name) / "client.crt"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "ed25519",
                "-nodes",
                "-keyout",
                str(cert.with_suffix(".key")),
                "-out",
                str(cert),
                "-days",
                "365",
                "-subj",
                "/CN=talos-backup-fixture",
            ],
            check=True,
            capture_output=True,
        )
        cls.certificate = base64.b64encode(cert.read_bytes()).decode()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="talos-backup-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        for name in ("bin", "work", "repository"):
            (self.root / name).mkdir(mode=0o700)
        password = self.root / "password"
        password.write_text("fixture-repository-password\n")
        password.chmod(0o600)
        config = self.root / "talosconfig"
        config.write_text(
            yaml.safe_dump(
                {
                    "context": "backup",
                    "contexts": {"backup": {"crt": self.certificate}},
                }
            )
        )
        config.chmod(0o600)
        self.environment = os.environ | {
            "PATH": str(self.root / "bin") + os.pathsep + os.environ["PATH"],
            "TALOSCONFIG": str(config),
            "TALOS_BACKUP_WORK_ROOT": str(self.root / "work"),
            "TALOS_BACKUP_EXPECTED_UUID": "fixture-ssd-uuid",
            "RESTIC_REPOSITORY": str(self.root / "repository"),
            "RESTIC_PASSWORD_FILE": str(password),
            "RESTIC_CACHE_DIR": str(self.root / "restic-cache"),
            "ANSIBLE_CONFIG": str(BACKUP.with_name("ansible.cfg")),
            "ANSIBLE_LOCAL_TEMP": str(self.root / "ansible-local"),
            "ANSIBLE_REMOTE_TEMP": str(self.root / "ansible-remote"),
            "ANSIBLE_PYTHON_INTERPRETER": sys.executable,
            "ANSIBLE_NOCOLOR": "true",
            "COPYFILE_DISABLE": "1",
            "TALOS_FIXTURE_ROOT": str(self.root),
            "TALOS_FIXTURE_MODE": "success",
        }
        self.tool("findmnt", "#!/bin/sh\nprintf '%s\\n' fixture-ssd-uuid\n")
        self.tool(
            "talosctl",
            """#!/usr/bin/env python3
import os,sys,pathlib
root=pathlib.Path(os.environ['TALOS_FIXTURE_ROOT'])
args=sys.argv[1:]; mode=os.environ['TALOS_FIXTURE_MODE']
if 'get' in args:
    counter=root/'reads'; count=int(counter.read_text())+1 if counter.exists() else 1
    counter.write_text(str(count))
    cp=args[args.index('--nodes')+1]=='10.0.70.11'
    kind='controlplane' if cp else 'worker'
    config='version: v1alpha1\\nmachine:\\n  type: '+kind+'\\n'
    if cp and mode!='redacted':
        config+='  ca:\\n    key: fixture-private-recovery-value\\ncluster:\\n  ca:\\n    key: fixture-private-cluster-value\\n'
    config+='---\\napiVersion: v1alpha1\\nkind: KmsgLogConfig\\nname: remote-log\\nurl: tcp://10.0.70.12:30515\\n'
    if mode=='changed' and count>2: config+='# concurrent configuration change\\n'
    print(config,end='')
elif 'snapshot' in args:
    if mode=='snapshot-failure': sys.exit(42)
    pathlib.Path(args[-1]).write_bytes(b'fixture-etcd-snapshot'*20)
elif 'version' in args: print('Talos v1.11.1 fixture')
else: sys.exit(43)
""",
        )
        subprocess.run(
            [str(self.restic), "init"],
            env=self.environment,
            check=True,
            capture_output=True,
        )

    def tool(self, name: str, content: str) -> None:
        path = self.root / "bin" / name
        path.write_text(content)
        path.chmod(0o700)

    def capture(self, mode: str = "success") -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ansible.cli.playbook",
                "-i",
                "localhost,",
                str(BACKUP),
            ],
            env=self.environment | {"TALOS_FIXTURE_MODE": mode},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=90,
        )
        self.assertNotIn("fixture-private-recovery-value", result.stdout)
        self.assertNotIn("fixture-private-cluster-value", result.stdout)
        return result

    def snapshots(self) -> list[dict[str, Any]]:
        return json.loads(
            subprocess.check_output(
                [str(self.restic), "snapshots", "--json"],
                env=self.environment,
                text=True,
            )
        )

    def seed_snapshot(self, age_days: int, tag: str = "talos-etcd") -> str:
        timestamp = (datetime.now() - timedelta(days=age_days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        result = subprocess.run(
            [
                str(self.restic),
                "backup",
                "--json",
                "--stdin",
                "--stdin-filename",
                "talos-etcd-recovery.tar",
                "--time",
                timestamp,
                "--host",
                "controller-fixture",
                "--tag",
                tag,
            ],
            input=b"retention recovery fixture",
            capture_output=True,
            check=True,
            env=self.environment,
        )
        reports = (json.loads(line) for line in result.stdout.splitlines())
        return next(
            report["snapshot_id"]
            for report in reports
            if report["message_type"] == "summary"
        )

    def test_capture_preserves_multidocument_configs_and_reads_back_the_bundle(self):
        result = self.capture()
        self.assertEqual(result.returncode, 0, result.stdout)
        receipt = (self.root / "work/last-success").read_text().strip()
        self.assertTrue(self.snapshots()[0]["id"].startswith(receipt))
        payload = subprocess.check_output(
            [str(self.restic), "dump", receipt, "/talos-etcd-recovery.tar"],
            env=self.environment,
        )
        with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
            files: dict[str, bytes] = {}
            for name in archive.getnames():
                source = archive.extractfile(name)
                self.assertIsNotNone(source)
                assert source is not None
                files[name] = source.read()
        self.assertEqual(
            set(files),
            {
                "etcd.snapshot",
                "controlplane.yaml",
                "worker.yaml",
                "versions.txt",
                "SHA256SUMS",
            },
        )
        docs = list(yaml.safe_load_all(files["controlplane.yaml"]))
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[1]["kind"], "KmsgLogConfig")
        self.assertIn(b"fixture-private-recovery-value", files["controlplane.yaml"])
        for line in files["SHA256SUMS"].decode().splitlines():
            digest, name = line.split()
            self.assertEqual(hashlib.sha256(files[name]).hexdigest(), digest)
        self.assertFalse(list((self.root / "work").glob("capture.*")))

    def test_redaction_or_config_changes_cannot_create_a_recovery_snapshot(self):
        for mode in ("redacted", "changed"):
            with self.subTest(mode=mode):
                (self.root / "reads").unlink(missing_ok=True)
                result = self.capture(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.root / "work/last-success").exists())
                self.assertEqual(self.snapshots(), [])
                self.assertTrue(list((self.root / "work").glob("capture.*")))

    def test_capture_failure_preserves_the_last_verified_snapshot(self):
        first = self.capture()
        self.assertEqual(first.returncode, 0, first.stdout)
        receipt = (self.root / "work/last-success").read_text()
        result = self.capture("snapshot-failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / "work/last-success").read_text(), receipt)
        self.assertEqual(len(self.snapshots()), 1)
        self.assertTrue(list((self.root / "work").glob("capture.*")))

    def test_failed_readback_cannot_advance_success_or_remove_private_staging(self):
        receipt = self.seed_snapshot(45) + "\n"
        (self.root / "work/last-success").write_text(receipt)
        self.tool(
            "restic",
            f"""#!/usr/bin/env python3
import os,sys
if sys.argv[1]=='restore': sys.exit(42)
os.execv({str(self.restic)!r},[{str(self.restic)!r}]+sys.argv[1:])
""",
        )
        result = self.capture()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / "work/last-success").read_text(), receipt)
        self.assertTrue(
            any(s["id"].startswith(receipt.strip()) for s in self.snapshots())
        )
        self.assertTrue(list((self.root / "work").glob("capture.*")))

    def test_retention_expires_old_copies_across_hosts_and_keeps_other_tags(self):
        old = self.seed_snapshot(45)
        recent = self.seed_snapshot(29)
        unrelated = self.seed_snapshot(60, "another-backup")
        result = self.capture()
        self.assertEqual(result.returncode, 0, result.stdout)
        ids = [s["id"] for s in self.snapshots()]
        for snapshot, kept in [(old, False), (recent, True), (unrelated, True)]:
            self.assertEqual(any(i.startswith(snapshot) for i in ids), kept)
        latest = (self.root / "work/last-success").read_text().strip()
        self.assertTrue(any(i.startswith(latest) for i in ids))

    def test_prune_failure_keeps_a_valid_receipt_after_expiring_old_snapshots(self):
        old = self.seed_snapshot(45)
        (self.root / "work/last-success").write_text(old + "\n")
        self.tool(
            "restic",
            f"""#!/usr/bin/env python3
import os,sys,subprocess
if sys.argv[1]=='forget':
    subprocess.run([{str(self.restic)!r}]+[a for a in sys.argv[1:] if a!='--prune'],check=True)
    sys.exit(42)
os.execv({str(self.restic)!r},[{str(self.restic)!r}]+sys.argv[1:])
""",
        )
        result = self.capture()
        self.assertNotEqual(result.returncode, 0)
        latest = (self.root / "work/last-success").read_text().strip()
        self.assertNotEqual(latest, old)
        ids = [s["id"] for s in self.snapshots()]
        self.assertFalse(any(i.startswith(old) for i in ids))
        self.assertTrue(any(i.startswith(latest) for i in ids))
        self.assertTrue(list((self.root / "work").glob("capture.*")))

    def test_wrong_mount_is_rejected_before_capture(self):
        self.environment["TALOS_BACKUP_EXPECTED_UUID"] = "another-ssd"
        result = self.capture()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "reads").exists())
        self.assertFalse(list((self.root / "work").glob("capture.*")))

    def test_missing_repository_is_not_automatically_initialized(self):
        self.environment["RESTIC_REPOSITORY"] = str(self.root / "absent-repository")
        result = self.capture()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "absent-repository/config").exists())
        self.assertFalse((self.root / "reads").exists())

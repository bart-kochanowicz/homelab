"""Check that image-scan exceptions stay narrow, explained and temporary."""

import datetime
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXCEPTIONS = ROOT / ".trivyignore-images.yaml"


class ImageScanExceptionTests(unittest.TestCase):
    def setUp(self):
        data = yaml.safe_load(EXCEPTIONS.read_text())
        self.assertEqual(set(data), {"vulnerabilities"})
        self.entries: list[dict[str, object]] = data["vulnerabilities"]

    def test_every_entry_is_scoped_to_package_versions(self):
        # An entry without purls would hide its CVE in every image.
        for entry in self.entries:
            with self.subTest(id=entry.get("id")):
                self.assertEqual(set(entry), {"id", "purls", "expired_at", "statement"})
                self.assertRegex(str(entry["id"]), r"^(CVE-\d{4}-\d+|GHSA-[\w-]+)$")
                purls = entry["purls"]
                self.assertIsInstance(purls, list)
                assert isinstance(purls, list)
                self.assertTrue(purls)
                for purl in purls:
                    self.assertRegex(str(purl), r"^pkg:[a-z]+/[^?#\s]+@[^?#\s]+$")

    def test_every_entry_expires_and_explains_itself(self):
        for entry in self.entries:
            with self.subTest(id=entry["id"]):
                self.assertIsInstance(entry["expired_at"], datetime.date)
                self.assertGreater(len(str(entry["statement"]).split()), 5)

    def test_the_image_scan_reads_the_exceptions(self):
        makefile = (ROOT / "Makefile").read_text()
        scan = re.search(r"^scan-images:.*?(?=^\S)", makefile, re.M | re.S)
        self.assertIsNotNone(scan)
        assert scan is not None
        self.assertIn("--ignorefile .trivyignore-images.yaml", scan.group(0))
        workflow = (ROOT / ".github/workflows/image-scan.yaml").read_text()
        self.assertIn(".trivyignore-images.yaml", workflow)

    def test_the_register_records_image_exceptions(self):
        register = (ROOT / "docs/exception-register.md").read_text()
        self.assertIn(".trivyignore-images.yaml", register)


if __name__ == "__main__":
    unittest.main()

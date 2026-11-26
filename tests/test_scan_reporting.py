"""Check that scheduled scan failures are tracked in one issue per scan."""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "scripts/scan_summary.py"
ISSUE = ROOT / "scripts/scan-issue.sh"
RUN = "https://github.com/bart-kochanowicz/homelab/actions/runs/1"


def vuln(vuln_id: str, severity: str, package: str = "openssl", fixed: str = "3.0.2"):
    return {
        "VulnerabilityID": vuln_id,
        "Severity": severity,
        "PkgName": package,
        "InstalledVersion": "3.0.1",
        "FixedVersion": fixed,
    }


class SummaryTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="homelab-scan-summary-")
        self.addCleanup(directory.cleanup)
        self.artifact = Path(directory.name)

    def summarize(self, kind: str) -> str:
        result = subprocess.run(
            [sys.executable, "-I", str(SUMMARY), kind, str(self.artifact), RUN],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def write(self, name: str, data: object):
        path = self.artifact / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))


class ImageSummaryTests(SummaryTestCase):
    def test_lists_critical_findings_and_unscanned_images(self):
        (self.artifact / "images.txt").write_text(
            "repo/app:1.0@sha256:aaaa\nrepo/broken:2.0@sha256:bbbb\n"
        )
        self.write(
            "reports/1.json",
            {
                "Results": [
                    {
                        "Vulnerabilities": [
                            vuln("CVE-1", "CRITICAL"),
                            vuln("CVE-2", "HIGH"),
                        ]
                    },
                    {"Vulnerabilities": [vuln("CVE-1", "CRITICAL")]},
                ]
            },
        )
        body = self.summarize("image")
        self.assertIn(RUN, body)
        self.assertIn(
            "| `repo/app:1.0` | `CVE-1` | `openssl` | `3.0.1` | `3.0.2` |", body
        )
        self.assertEqual(body.count("`CVE-1`"), 1)
        self.assertNotIn("CVE-2", body)
        self.assertIn("- `repo/broken:2.0`", body)

    def test_a_missing_inventory_points_to_the_run(self):
        body = self.summarize("image")
        self.assertIn(RUN, body)
        self.assertIn("no image inventory", body)

    def test_scanner_text_cannot_break_the_table_or_mention_anyone(self):
        (self.artifact / "images.txt").write_text("repo/app:1.0\n")
        package = "evil|`pkg`\n@someone"
        self.write(
            "reports/1.json",
            {"Results": [{"Vulnerabilities": [vuln("CVE-1", "CRITICAL", package)]}]},
        )
        body = self.summarize("image")
        row = next(line for line in body.splitlines() if "CVE-1" in line)
        self.assertEqual(row.count("|"), 6)
        self.assertIn("`evilpkg @someone`", row)

    def test_a_long_body_is_cut_below_the_issue_limit(self):
        (self.artifact / "images.txt").write_text("repo/app:1.0\n")
        vulns = [vuln(f"CVE-{index}", "CRITICAL") for index in range(2000)]
        self.write("reports/1.json", {"Results": [{"Vulnerabilities": vulns}]})
        body = self.summarize("image")
        self.assertLess(len(body), 65536)
        self.assertIn("cut short", body)


class DependencySummaryTests(SummaryTestCase):
    def test_lists_high_and_critical_findings_without_fixes(self):
        self.write(
            "report.json",
            {
                "Results": [
                    {
                        "Vulnerabilities": [
                            vuln("CVE-1", "HIGH", "pyyaml", fixed=""),
                            vuln("CVE-2", "MEDIUM", "ruff"),
                        ]
                    }
                ]
            },
        )
        body = self.summarize("dependency")
        self.assertIn("| `pyyaml` | `3.0.1` | `none` | `HIGH` | `CVE-1` |", body)
        self.assertNotIn("ruff", body)

    def test_a_missing_report_points_to_the_run(self):
        body = self.summarize("dependency")
        self.assertIn(RUN, body)
        self.assertIn("no report", body)


class IssueScriptTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="homelab-scan-issue-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(
            f"#!{sys.executable}\n"
            + textwrap.dedent("""\
                import json, os, sys
                from pathlib import Path
                with Path(os.environ["GH_LOG"]).open("a") as log:
                    log.write(json.dumps(sys.argv[1:]) + "\\n")
                if sys.argv[1:3] == ["issue", "list"]:
                    print(os.environ["GH_ISSUES"])
                """)
        )
        gh.chmod(0o755)
        self.log = self.root / "gh.log"
        self.body = self.root / "body.md"
        self.body.write_text("findings\n")
        self.environment = os.environ | {
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
            "GH_LOG": str(self.log),
        }

    def run_script(
        self, issues: list[dict[str, object]], *args: str
    ) -> list[list[str]]:
        subprocess.run(
            [str(ISSUE), *args],
            env=self.environment | {"GH_ISSUES": json.dumps(issues)},
            check=True,
            capture_output=True,
            text=True,
        )
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [call for call in calls if call[:2] != ["issue", "list"]]

    def test_a_first_failure_opens_a_labelled_issue(self):
        other = [{"number": 7, "title": "Scheduled dependency scan fails"}]
        calls = self.run_script(
            other, "open", "Scheduled image scan fails", str(self.body), RUN
        )
        self.assertEqual(calls[0][:3], ["label", "create", "scan-failure"])
        self.assertEqual(
            calls[1],
            [
                "issue",
                "create",
                "--title",
                "Scheduled image scan fails",
                "--label",
                "scan-failure",
                "--body-file",
                str(self.body),
            ],
        )
        self.assertEqual(len(calls), 2)

    def test_a_repeated_failure_updates_the_open_issue(self):
        issues = [{"number": 12, "title": "Scheduled image scan fails"}]
        calls = self.run_script(
            issues, "open", "Scheduled image scan fails", str(self.body), RUN
        )
        self.assertEqual(
            calls,
            [
                ["issue", "edit", "12", "--body-file", str(self.body)],
                [
                    "issue",
                    "comment",
                    "12",
                    "--body",
                    f"The scan failed again in {RUN}.",
                ],
            ],
        )

    def test_a_passing_scan_closes_its_issue_only(self):
        issues = [
            {"number": 7, "title": "Scheduled dependency scan fails"},
            {"number": 12, "title": "Scheduled image scan fails"},
        ]
        calls = self.run_script(issues, "close", "Scheduled image scan fails", RUN)
        self.assertEqual(
            calls,
            [["issue", "close", "12", "--comment", f"The scan passes again in {RUN}."]],
        )

    def test_a_passing_scan_without_an_issue_does_nothing(self):
        calls = self.run_script([], "close", "Scheduled image scan fails", RUN)
        self.assertEqual(calls, [])


class WorkflowTests(unittest.TestCase):
    WORKFLOWS = {
        "image-scan.yaml": ("scan", "image-scan", "image"),
        "dependency-scan.yaml": ("scan-dependencies", "dependency-scan", "dependency"),
    }

    def test_only_the_report_job_writes_issues(self):
        for name, (scan, artifact, kind) in self.WORKFLOWS.items():
            with self.subTest(workflow=name):
                workflow = yaml.safe_load(
                    (ROOT / ".github/workflows" / name).read_text()
                )
                self.assertEqual(workflow["permissions"], {"contents": "read"})
                jobs = workflow["jobs"]
                self.assertNotIn("permissions", jobs[scan])
                report = jobs["report"]
                self.assertEqual(report["needs"], scan)
                self.assertEqual(
                    report["permissions"], {"contents": "read", "issues": "write"}
                )
                condition = report["if"]
                for clause in (
                    "always()",
                    "github.ref == 'refs/heads/main'",
                    "github.event_name != 'pull_request'",
                    "github.repository == 'bart-kochanowicz/homelab'",
                    f"(needs.{scan}.result == 'success' || needs.{scan}.result == 'failure')",
                ):
                    self.assertIn(clause, condition)
                self.assertEqual(
                    report["concurrency"],
                    {
                        "group": "scan-issue-${{ github.workflow }}",
                        "cancel-in-progress": False,
                    },
                )
                steps = {step["name"]: step for step in report["steps"]}
                checkout = steps["Check out repository"]
                self.assertIs(checkout["with"]["persist-credentials"], False)
                download = steps["Download scan results"]
                self.assertEqual(download["with"]["name"], artifact)
                upload = next(
                    step
                    for step in jobs[scan]["steps"]
                    if "upload-artifact" in step.get("uses", "")
                )
                self.assertEqual(upload["with"]["name"], artifact)
                script = steps["Open, update or close the scan issue"]["run"]
                self.assertIn(f"scripts/scan_summary.py {kind} ", script)
                self.assertIn(f'title="Scheduled {kind} scan fails"', script)


if __name__ == "__main__":
    unittest.main()

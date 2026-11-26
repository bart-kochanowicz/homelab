"""Turn image or dependency scan artifacts into a Markdown issue body.

Usage: scan_summary.py image|dependency ARTIFACT_DIR RUN_URL

ARTIFACT_DIR is the downloaded scan artifact: `images.txt` and `reports/` for
images, `report.json` for dependencies. Missing files are reported, not raised,
so a broken scan still produces an issue that points to its run.
"""

import json
import sys
from pathlib import Path
from typing import Any

# GitHub rejects issue bodies over 65536 characters.
LIMIT = 60000


def code(value: object) -> str:
    """Quote untrusted scanner text so it cannot break the table or mention anyone."""
    text = " ".join(str(value).replace("`", "").replace("|", "").split())
    return f"`{text}`" if text else ""


def load(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def findings(
    report: dict[str, Any], severities: set[str]
) -> set[tuple[str, str, str, str, str]]:
    rows: set[tuple[str, str, str, str, str]] = set()
    results: list[dict[str, Any]] = report.get("Results") or []
    for result in results:
        vulns: list[dict[str, Any]] = result.get("Vulnerabilities") or []
        for vuln in vulns:
            if vuln.get("Severity") in severities:
                rows.add(
                    (
                        vuln.get("Severity", ""),
                        vuln.get("VulnerabilityID", ""),
                        vuln.get("PkgName", ""),
                        vuln.get("InstalledVersion", ""),
                        vuln.get("FixedVersion") or "none",
                    )
                )
    return rows


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    lines.extend("| " + " | ".join(code(cell) for cell in row) + " |" for row in rows)
    return lines


def image_summary(artifact: Path) -> list[str]:
    inventory = artifact / "images.txt"
    try:
        images = [line for line in inventory.read_text().splitlines() if line.strip()]
    except OSError:
        return ["The scan produced no image inventory; the run log shows why."]
    rows: list[list[str]] = []
    unscanned: list[str] = []
    for index, image in enumerate(images, start=1):
        report = load(artifact / "reports" / f"{index}.json")
        name = image.split("@")[0]
        if report is None:
            unscanned.append(name)
            continue
        for _, vuln_id, package, installed, fixed in sorted(
            findings(report, {"CRITICAL"})
        ):
            rows.append([name, vuln_id, package, installed, fixed])
    lines: list[str] = []
    if rows:
        lines += ["Fixable CRITICAL vulnerabilities:", ""]
        lines += table(
            ["Image", "Vulnerability", "Package", "Installed", "Fixed"], rows
        )
    if unscanned:
        lines += ["", "Images that could not be scanned:", ""]
        lines += [f"- {code(name)}" for name in unscanned]
    if not lines:
        lines = [
            "The reports list no CRITICAL findings; the run log shows why it failed."
        ]
    lines += [
        "",
        "Update the image, or add a reviewed exception to `.trivyignore-images.yaml`",
        "and `docs/exception-register.md` (see `docs/security-runbook.md`).",
    ]
    return lines


def dependency_summary(artifact: Path) -> list[str]:
    report = load(artifact / "report.json")
    if report is None:
        return ["The scan produced no report; the run log shows why."]
    rows = [
        [package, installed, fixed, severity, vuln_id]
        for severity, vuln_id, package, installed, fixed in sorted(
            findings(report, {"HIGH", "CRITICAL"}), key=lambda row: (row[2], row[1])
        )
    ]
    if not rows:
        return [
            "The report lists no HIGH or CRITICAL findings; the run log shows why it failed."
        ]
    return [
        "HIGH and CRITICAL vulnerabilities in `uv.lock`:",
        "",
        *table(["Package", "Installed", "Fixed", "Severity", "Vulnerability"], rows),
        "",
        "Update the package with `uv lock --upgrade-package <name>`.",
    ]


def summary(kind: str, artifact: Path, run_url: str) -> str:
    lines = {"image": image_summary, "dependency": dependency_summary}[kind](artifact)
    head = f"The {kind} scan on `main` failed in {run_url}."
    body = "\n".join([head, "", *lines]) + "\n"
    if len(body) > LIMIT:
        cut = body.rfind("\n", 0, LIMIT)
        body = (
            body[:cut]
            + "\n\nThe list is cut short; the run artifact has every finding.\n"
        )
    return body


def main() -> None:
    if len(sys.argv) != 4 or sys.argv[1] not in {"image", "dependency"}:
        raise SystemExit(__doc__)
    sys.stdout.write(summary(sys.argv[1], Path(sys.argv[2]), sys.argv[3]))


if __name__ == "__main__":
    main()

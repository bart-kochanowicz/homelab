"""PostToolUse check: format and lint the file an agent just changed.

Terraform and Python files are formatted in place. YAML, shell and JSON
problems are reported back to the agent (exit code 2) so it fixes them before
moving on. Missing tools are skipped; `make validate` remains the full check.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKIPPED_YAML = ("/charts/", "/templates/", "/.terraform/")


def run(
    command: list[str], cwd: Path, stdin: str | None = None
) -> subprocess.CompletedProcess[str] | None:
    if shutil.which(command[0]) is None:
        return None
    return subprocess.run(
        command, cwd=cwd, input=stdin, capture_output=True, text=True, timeout=120
    )


def problems(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    name = path.name
    if name.endswith((".tf", ".tftest.hcl")):
        result = run(["terraform", "fmt", "-list=false", rel], root)
        return result.stderr if result and result.returncode else ""
    if name.endswith((".tfbackend", ".tfvars.example")):
        # terraform fmt accepts these HCL files only on stdin.
        original = path.read_text()
        result = run(["terraform", "fmt", "-"], root, original)
        if result and result.returncode:
            return f"{rel}: {result.stderr}"
        if result and result.stdout != original:
            path.write_text(result.stdout)
        return ""
    if name.endswith(".py") and (
        rel.startswith("tests/") or rel.startswith(".claude/hooks/")
    ):
        run(["uv", "run", "--locked", "ruff", "format", "--quiet", rel], root)
        # An import added in one edit is often used only by the next one, so unused
        # imports are left alone here; `make validate-python` still reports them.
        command = ["ruff", "check", "--fix", "--quiet", "--ignore", "F401", rel]
        result = run(["uv", "run", "--locked", *command], root)
        return result.stdout + result.stderr if result and result.returncode else ""
    if name.endswith((".yaml", ".yml")) and not any(
        part in f"/{rel}" for part in SKIPPED_YAML
    ):
        result = run(["yamllint", "-f", "parsable", "-c", ".yamllint.yaml", rel], root)
        return result.stdout if result and result.returncode else ""
    if name.endswith(".sh"):
        result = run(["shellcheck", "-f", "gcc", rel], root)
        return result.stdout if result and result.returncode else ""
    if name.endswith(".json"):
        try:
            json.loads(path.read_text())
        except ValueError as error:
            return f"{rel}: invalid JSON: {error}"
    return ""


def main() -> int:
    payload = json.load(sys.stdin)
    data = payload.get("tool_input") or {}
    root = Path(
        os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "."
    ).resolve()
    raw = data.get("file_path") if isinstance(data, dict) else None
    if not isinstance(raw, str):
        return 0
    path = (
        (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
    )
    if not path.is_file() or not path.is_relative_to(root):
        return 0
    if report := problems(path, root).strip():
        print(report, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

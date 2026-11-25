"""Run Claude Code hook scripts the way Claude Code does."""

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".claude" / "hooks"


def run_hook(
    script: str, payload: Mapping[str, object], project: Path = ROOT
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(HOOKS / script)],
        input=json.dumps(dict(payload)),
        # uv runs the repository's locked tools even in a temporary project.
        env=os.environ | {"CLAUDE_PROJECT_DIR": str(project), "UV_PROJECT": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def decision(tool: str, tool_input: Mapping[str, object], project: Path = ROOT) -> str:
    """Return the guard's permission decision, or "" when it stays silent."""
    result = run_hook(
        "guard.py",
        {"tool_name": tool, "tool_input": tool_input, "cwd": str(project)},
        project,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    if not result.stdout:
        return ""
    output: dict[str, dict[str, str]] = json.loads(result.stdout)
    return output["hookSpecificOutput"]["permissionDecision"]

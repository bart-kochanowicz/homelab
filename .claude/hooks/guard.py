"""PreToolUse guard: keep agents away from private files and live changes.

Claude Code sends the tool call as JSON on stdin. The guard prints a
permission decision for calls it recognizes and stays silent otherwise.
Commands are parsed on a best-effort basis: this is a guardrail against
mistakes, not a sandbox, so permissions and reviewed plans still apply.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Literal, NamedTuple


class Decision(NamedTuple):
    kind: Literal["ask", "deny"]
    reason: str

    def render(self) -> dict[str, object]:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": self.kind,
                "permissionDecisionReason": self.reason,
            }
        }


def deny(reason: str) -> Decision:
    return Decision("deny", reason)


def ask(reason: str) -> Decision:
    return Decision("ask", reason)


PRIVATE_PATHS = (
    (r"(^|/)\.secrets(/|$)", "holds private credentials"),
    (r"(^|/)[^/]+\.tfstate(\.backup)?$", "is Terraform state"),
    (r"(^|/)[^/]+\.tfplan$", "is a saved Terraform plan with credentials"),
    (
        r"(^|/)talos/(controlplane\.yaml|worker\.yaml|talosconfig)$",
        "is a Talos config with credentials",
    ),
    (
        r"(^|/)infra/unifi/(backups|private)(/|$)",
        "holds UniFi or GPON recovery material",
    ),
    (r"(^|/)\.backups(/|$)", "holds local backup material"),
    (r"(^|/)[^/]+\.(restic-password|pem|key)$", "is key material"),
)
LOCAL_INPUTS = r"(^|/)[^/]+\.tfvars(\.json)?$"

ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Commands that run another command, with the flags that take a value.
WRAPPERS: dict[str, set[str]] = {
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-U", "-r", "-t", "-D"},
    "env": {"-u", "-C", "-S"},
    "nice": {"-n"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "time": set(),
    "nohup": set(),
    "command": set(),
    "exec": {"-a"},
    "xargs": {"-I", "-n", "-P", "-L", "-d", "-E", "-s"},
    "caffeinate": {"-t", "-w"},
}
# Wrappers whose first positional argument is not the command (the duration).
WRAPPER_POSITIONALS = {"timeout": 1}
# Tool runners: `aqua exec -- terraform`, `uv run --locked kubectl`.
RUNNERS = {"aqua": "exec", "uv": "run", "pnpm": "exec"}
RUNNER_VALUE_FLAGS = {
    "--with",
    "--python",
    "-p",
    "--project",
    "--directory",
    "--group",
    "--extra",
    "--env-file",
    "--package",
    "--index",
}
SHELLS = {"bash", "sh", "zsh"}
SHELL_COMMAND_FLAG = re.compile(r"^-[A-Za-z]*c[A-Za-z]*$")
PUNCTUATION = ";&|()\n"

KUBECTL_VALUE_FLAGS = {
    "-n",
    "--namespace",
    "--context",
    "--kubeconfig",
    "--cluster",
    "--user",
    "-s",
    "--server",
    "--as",
    "--as-group",
    "--token",
    "--request-timeout",
    "-l",
    "--selector",
    "--field-selector",
    "-f",
    "--filename",
    "-o",
    "--output",
    "-c",
    "--container",
}
KUBECTL_ROLLOUT_READS = {"status", "history"}
KUBECTL_SECRET_KINDS = re.compile(r"^(secrets?|sealedsecrets?)([/.]|$)")
KUBECTL_MUTATING = {
    "apply",
    "create",
    "delete",
    "edit",
    "patch",
    "replace",
    "scale",
    "rollout",
    "label",
    "annotate",
    "drain",
    "cordon",
    "uncordon",
    "taint",
    "set",
    "exec",
    "cp",
    "run",
    "expose",
    "autoscale",
    "debug",
}
KUBECTL_DATA_KINDS = re.compile(
    r"^(ns|namespaces?|pvc|persistentvolumeclaims?|pv|persistentvolumes?)([/.]|$)"
)
TALOSCTL_VALUE_FLAGS = {
    "-n",
    "--nodes",
    "-e",
    "--endpoints",
    "--talosconfig",
    "--context",
}
TALOSCTL_MUTATING = {
    "apply-config",
    "apply",
    "upgrade",
    "upgrade-k8s",
    "reboot",
    "shutdown",
    "bootstrap",
    "patch",
    "edit",
    "rotate-ca",
}
TALOSCTL_ETCD_READS = {"snapshot", "status", "members", "alarm"}
HELM_VALUE_FLAGS = {"-n", "--namespace", "--kube-context", "--kubeconfig"}
HELM_MUTATING = {"install", "upgrade", "uninstall", "delete", "rollback"}
ARGOCD_MUTATING = {
    "sync",
    "delete",
    "set",
    "unset",
    "patch",
    "rollback",
    "terminate-op",
    "create",
    "add",
    "rm",
}
GH_VALUE_FLAGS = {"-R", "--repo", "-e", "--env", "-o", "--org"}
TERRAFORM_STATE_CHANGES = {"import", "taint", "untaint", "force-unlock", "refresh"}
TERRAFORM_STATE_SUBCOMMANDS = {"rm", "mv", "push", "replace-provider"}
ANSIBLE_DRY_RUN = {"--check", "-C", "--syntax-check", "--list-tasks", "--list-hosts"}


def relative(path: str, root: Path) -> str:
    """Return the path relative to the project, without following symlinks.

    Worktrees link private files such as `.secrets` from the main checkout,
    so the link's own path is what identifies them.
    """
    candidate = os.path.normpath(os.path.join(root, path))
    base = os.path.normpath(root)
    if candidate == base or candidate.startswith(base + os.sep):
        return PurePosixPath(os.path.relpath(candidate, base)).as_posix()
    return PurePosixPath(candidate).as_posix()


def check_path(path: str, root: Path) -> Decision | None:
    rel = relative(path, root)
    for pattern, why in PRIVATE_PATHS:
        if re.search(pattern, rel):
            return deny(
                f"{rel} {why}; agents must not read or change it. Ask the user."
            )
    if re.search(LOCAL_INPUTS, rel):
        return ask(
            f"{rel} holds local provider credentials; confirm the agent may open it."
        )
    return None


def plaintext_secret(text: str) -> bool:
    """Return whether YAML text contains a Kubernetes Secret with data."""
    for document in re.split(r"(?m)^---\s*$", text):
        if re.search(r"(?m)^kind:\s*[\"']?Secret[\"']?\s*$", document) and re.search(
            r"(?m)^(data|stringData):", document
        ):
            return True
    return False


def edited_text(tool: str, data: dict[str, object], target: Path) -> str | None:
    """Return the file content the Write, Edit or MultiEdit call would produce."""
    if tool == "Write":
        content = data.get("content")
        return content if isinstance(content, str) else None
    raw = data.get("edits") if tool == "MultiEdit" else [data]
    edits: list[object] = list(raw) if isinstance(raw, list) else []
    try:
        text = target.read_text()
    except OSError:
        text = ""
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        old, new = edit.get("old_string"), edit.get("new_string")
        if isinstance(old, str) and isinstance(new, str):
            text = text.replace(old, new, -1 if edit.get("replace_all") else 1)
    return text


def check_file_tool(tool: str, data: dict[str, object], root: Path) -> Decision | None:
    path = data.get("file_path") or data.get("notebook_path")
    if not isinstance(path, str) or not path:
        return None
    if result := check_path(path, root):
        return result
    if tool in {"Write", "Edit", "MultiEdit"} and re.search(r"\.ya?ml$", path):
        target = Path(path) if Path(path).is_absolute() else root / path
        text = edited_text(tool, data, target)
        if text and plaintext_secret(text):
            return deny(
                f"{relative(path, root)} would contain a plaintext Kubernetes Secret. "
                "Commit a strict-scope SealedSecret instead; see the seal-secret skill."
            )
    return None


def segments(command: str) -> Iterator[list[str]]:
    """Split a shell command into simple commands at separators."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=PUNCTUATION)
    lexer.whitespace_split = True
    lexer.commenters = ""
    current: list[str] = []
    for token in lexer:
        if set(token) <= set(PUNCTUATION):
            if current:
                yield current
            current = []
        else:
            current.append(token)
    if current:
        yield current


def strip_prefix(words: list[str]) -> list[str]:
    """Drop environment assignments, wrappers such as sudo and tool runners."""
    index = 0
    while index < len(words):
        word = words[index]
        name = PurePosixPath(word).name
        if ENV_ASSIGNMENT.match(word):
            index += 1
            continue
        if name in WRAPPERS:
            flags, positionals = WRAPPERS[name], WRAPPER_POSITIONALS.get(name, 0)
            index += 1
        elif name in RUNNERS and words[index + 1 : index + 2] == [RUNNERS[name]]:
            flags, positionals = RUNNER_VALUE_FLAGS, 0
            index += 2
        else:
            break
        while index < len(words):
            arg = words[index]
            if arg == "--":
                index += 1
                break
            if arg in flags:
                index += 2
            elif arg.startswith("-") or (name == "env" and ENV_ASSIGNMENT.match(arg)):
                index += 1
            elif positionals:
                positionals -= 1
                index += 1
            else:
                break
    return words[index:]


def positional(args: list[str], value_flags: set[str] | None = None) -> list[str]:
    """Return arguments that are not flags or flag values."""
    flags = value_flags or set()
    result: list[str] = []
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg in flags:
            skip = True
        elif not arg.startswith("-"):
            result.append(arg)
    return result


def check_make(args: list[str], cwd: str) -> Decision | None:
    directory = PurePosixPath(cwd)
    makefile = ""
    targets: list[str] = []
    pending = ""
    for arg in args:
        if pending == "dir":
            directory = directory / arg
        elif pending == "file":
            makefile = arg
        elif arg in {"-C", "--directory"}:
            pending = "dir"
            continue
        elif arg in {"-f", "--file", "--makefile"}:
            pending = "file"
            continue
        elif arg.startswith("--directory="):
            directory = directory / arg.split("=", 1)[1]
        elif arg.startswith("-C"):
            directory = directory / arg[2:]
        elif arg.startswith(("--file=", "--makefile=")):
            makefile = arg.split("=", 1)[1]
        elif not arg.startswith("-") and "=" not in arg:
            targets.append(arg)
        pending = ""
    if directory.name == "system" or PurePosixPath(makefile).parent.name == "system":
        if {"clean", "force-clean"} & set(targets):
            return deny(
                "system clean targets delete ArgoCD and its Applications. Ask the user to run them."
            )
        return ask(
            "system/Makefile targets bootstrap ArgoCD or Cilium on the live cluster."
        )
    at_root = directory == PurePosixPath(cwd) and not makefile
    if at_root and (not targets or {"system", "default"} & set(targets)):
        return deny(
            "Bare `make` runs ArgoCD bootstrap against the live cluster. "
            "Use `make validate` or a focused target to check changes."
        )
    return None


def check_terraform(args: list[str]) -> Decision | None:
    sub = positional(args)
    verb, rest = (sub[0], sub[1:]) if sub else ("", [])
    if verb in {"apply", "destroy"}:
        return deny(
            "Terraform applies run only from the reviewed GitHub Actions plan. "
            "Plan locally with read-only access; see terraform/README.md."
        )
    if verb in TERRAFORM_STATE_CHANGES or (
        verb == "state" and rest[:1] and rest[0] in TERRAFORM_STATE_SUBCOMMANDS
    ):
        return ask(f"`terraform {' '.join(sub[:2])}` changes remote state in Garage.")
    if verb == "workspace" and rest[:1] and rest[0] in {"new", "delete", "select"}:
        return ask("The repository uses only the default Terraform workspace.")
    if verb == "init" and {"-migrate-state", "-force-copy"} & set(args):
        return ask("`terraform init -migrate-state` can overwrite remote state.")
    return None


def check_kubectl(args: list[str]) -> Decision | None:
    if any(arg.startswith("--dry-run") and not arg.endswith("=none") for arg in args):
        return None
    sub = positional(args, KUBECTL_VALUE_FLAGS)
    verb = sub[0] if sub else ""
    kinds = sub[1].lower().split(",") if len(sub) > 1 else []
    if verb == "get" and any(KUBECTL_SECRET_KINDS.match(kind) for kind in kinds):
        return ask("`kubectl get secret` can print credentials into the conversation.")
    if verb == "rollout" and sub[1:2] and sub[1] in KUBECTL_ROLLOUT_READS:
        return None
    if verb == "delete":
        if any(KUBECTL_DATA_KINDS.match(kind) for kind in kinds) or {
            "--all",
            "--all-namespaces",
            "-A",
        } & set(args):
            return deny(
                "Deleting namespaces, volumes or every resource loses data. Ask the user to run it."
            )
    if verb in KUBECTL_MUTATING:
        return ask(f"`kubectl {verb}` changes the live cluster outside ArgoCD.")
    return None


def check_talosctl(args: list[str]) -> Decision | None:
    sub = positional(args, TALOSCTL_VALUE_FLAGS)
    verb = sub[0] if sub else ""
    if verb in {"reset", "wipe"}:
        return deny(f"`talosctl {verb}` wipes a node or disk. Ask the user to run it.")
    if verb in TALOSCTL_MUTATING or (
        verb == "etcd" and not (sub[1:2] and sub[1] in TALOSCTL_ETCD_READS)
    ):
        return ask(f"`talosctl {verb}` changes a Talos node or etcd.")
    return None


def check_tool(tool: str, args: list[str], cwd: str) -> Decision | None:
    if tool == "terraform":
        return check_terraform(args)
    if tool == "kubectl":
        return check_kubectl(args)
    if tool == "talosctl":
        return check_talosctl(args)
    if tool == "make":
        return check_make(args, cwd)
    if tool == "helm":
        sub = positional(args, HELM_VALUE_FLAGS)
        if sub[:1] and sub[0] in HELM_MUTATING:
            return ask(f"`helm {sub[0]}` changes the live cluster outside ArgoCD.")
    if tool == "cilium":
        sub = positional(args)
        if sub[:1] and sub[0] in {"install", "upgrade", "uninstall"}:
            return ask(
                "Cilium is bootstrap-managed; use `make -C system bootstrap-cilium`."
            )
    if tool == "argocd":
        sub = positional(args)
        if len(sub) > 1 and sub[1] in ARGOCD_MUTATING:
            return ask(f"`argocd {sub[0]} {sub[1]}` changes ArgoCD state.")
    if tool in {"ansible-playbook", "ansible"} and not ANSIBLE_DRY_RUN & set(args):
        return ask("Ansible changes Houston or the cluster; dry runs use --check.")
    if tool == "gh":
        sub = positional(args, GH_VALUE_FLAGS)
        if (
            len(sub) > 1
            and sub[0] in {"secret", "variable"}
            and sub[1] in {"set", "delete", "remove"}
        ):
            return ask(f"`gh {sub[0]} {sub[1]}` changes a private Actions input.")
    removes = tool in {"rm", "unlink"} or (tool == "git" and args[:1] == ["rm"])
    if removes and any(arg.endswith(".terraform.lock.hcl") for arg in args):
        return deny(
            "Provider lock files stay tracked; fix the error instead of deleting the lock."
        )
    return None


def mentions_private_path(words: list[str]) -> Decision | None:
    """Ask before a shell command that names a private file or directory."""
    for word in words:
        if any(re.search(pattern, word) for pattern, _ in PRIVATE_PATHS):
            return ask(f"The command touches {word}, which holds private material.")
        if re.search(LOCAL_INPUTS, word):
            return ask(f"The command touches {word}, which holds local credentials.")
    return None


def check_command(command: str, cwd: str) -> Decision | None:
    """Return the strictest decision for any simple command in the string."""
    try:
        parts = list(segments(command))
    except ValueError:
        parts = [command.split()]
    asked: Decision | None = None
    for words in parts:
        if words[:1] == ["cd"] and len(words) > 1:
            cwd = str(PurePosixPath(cwd) / words[1])
            continue
        words = strip_prefix(words)
        if not words:
            continue
        tool, args = PurePosixPath(words[0]).name, words[1:]
        flag = next((a for a in args[:-1] if SHELL_COMMAND_FLAG.match(a)), None)
        if tool in SHELLS and flag:
            result = check_command(args[args.index(flag) + 1], cwd)
        else:
            result = check_tool(tool, args, cwd) or mentions_private_path(words)
        if result and result.kind == "deny":
            return result
        asked = asked or result
    return asked


def evaluate(payload: dict[str, object], project: Path) -> Decision | None:
    tool, data = payload.get("tool_name"), payload.get("tool_input")
    if not isinstance(tool, str) or not isinstance(data, dict):
        return None
    if tool == "Bash":
        command = data.get("command")
        cwd = str(payload.get("cwd") or project)
        return check_command(command, cwd) if isinstance(command, str) else None
    if tool in {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit"}:
        return check_file_tool(tool, data, project)
    if tool in {"Grep", "Glob"}:
        path = data.get("path")
        return check_path(path, project) if isinstance(path, str) and path else None
    return None


def main() -> int:
    payload = json.load(sys.stdin)
    project = Path(
        os.environ.get("CLAUDE_PROJECT_DIR") or str(payload.get("cwd") or ".")
    )
    if result := evaluate(payload, project):
        json.dump(result.render(), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())

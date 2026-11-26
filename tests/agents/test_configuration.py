"""Check that agent skills, subagents, hooks and OpenSpec are wired together."""

import json
import re
import unittest
from pathlib import Path

import yaml

from .support import ROOT

SKILLS = ROOT / ".agents" / "skills"
CLAUDE_SKILLS = ROOT / ".claude" / "skills"


def frontmatter(path: Path) -> dict[str, object]:
    match = re.match(r"^---\n(.*?)\n---\n", path.read_text(), re.S)
    if not match:
        raise AssertionError(f"{path} has no frontmatter")
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise AssertionError(f"{path} frontmatter is not a mapping")
    return {str(key): value for key, value in data.items()}


class SkillTests(unittest.TestCase):
    def skill_dirs(self) -> list[Path]:
        return sorted(path for path in SKILLS.iterdir() if path.is_dir())

    def test_every_skill_names_itself_and_says_when_to_use_it(self):
        for skill in self.skill_dirs():
            with self.subTest(skill=skill.name):
                meta = frontmatter(skill / "SKILL.md")
                self.assertEqual(meta.get("name"), skill.name)
                description = meta.get("description")
                self.assertIsInstance(description, str)
                self.assertTrue(str(description).strip())

    def test_claude_code_links_every_skill_and_nothing_else(self):
        links = {path.name: path for path in CLAUDE_SKILLS.iterdir()}
        self.assertEqual(set(links), {skill.name for skill in self.skill_dirs()})
        for name, link in links.items():
            with self.subTest(skill=name):
                self.assertTrue(link.is_symlink())
                self.assertEqual(link.readlink(), Path("../../.agents/skills") / name)

    def test_copied_skills_record_their_source(self):
        notice = (SKILLS / "THIRD_PARTY.md").read_text()
        authored = {
            "add-application",
            "platform-sync",
            "seal-secret",
            "terraform-plan-review",
            "unifi-reservations",
        }
        for skill in self.skill_dirs():
            if skill.name in authored or skill.name.startswith("openspec-"):
                continue
            with self.subTest(skill=skill.name):
                self.assertIn(f"| `{skill.name}` |", notice)


class SubagentTests(unittest.TestCase):
    def test_subagents_are_read_only_reporters(self):
        agents = sorted((ROOT / ".claude" / "agents").glob("*.md"))
        self.assertEqual([agent.stem for agent in agents], ["reviewer", "verifier"])
        for agent in agents:
            with self.subTest(agent=agent.stem):
                meta = frontmatter(agent)
                self.assertEqual(meta.get("name"), agent.stem)
                self.assertTrue(str(meta.get("description", "")).strip())
                tools = {tool.strip() for tool in str(meta.get("tools", "")).split(",")}
                self.assertFalse(tools & {"Edit", "Write", "MultiEdit", "NotebookEdit"})


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.settings: dict[str, dict[str, list[dict[str, object]]]] = json.loads(
            (ROOT / ".claude" / "settings.json").read_text()
        )

    def test_hooks_run_scripts_that_exist(self):
        commands = [
            str(hook["command"])
            for groups in self.settings["hooks"].values()
            for group in groups
            for hook in group["hooks"]  # type: ignore[union-attr]
        ]
        self.assertTrue(commands)
        for command in commands:
            with self.subTest(command=command):
                script = re.search(r"\.claude/hooks/[\w.]+", command)
                self.assertIsNotNone(script)
                assert script is not None
                self.assertTrue((ROOT / script.group(0)).is_file())

    def test_guard_covers_shell_and_file_tools(self):
        matchers = {
            str(group["matcher"]) for group in self.settings["hooks"]["PreToolUse"]
        }
        covered = {tool for matcher in matchers for tool in matcher.split("|")}
        self.assertLessEqual({"Bash", "Read", "Edit", "Write", "MultiEdit"}, covered)

    def test_focused_validate_targets_run_without_a_prompt(self):
        # `Bash(make validate:*)` matches only at a word boundary, so it would
        # leave `make validate-workflows` and the other targets prompting.
        allow = self.settings["permissions"]["allow"]
        self.assertIn("Bash(make validate*)", allow)
        self.assertNotIn("Bash(make validate:*)", allow)


class OpenSpecTests(unittest.TestCase):
    def test_makefile_and_ci_pin_the_same_cli_version(self):
        makefile = re.search(
            r"^OPENSPEC_VERSION := (\S+)$", (ROOT / "Makefile").read_text(), re.M
        )
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/validate.yaml").read_text()
        )
        install = next(
            step
            for step in workflow["jobs"]["validate"]["steps"]
            if step["name"] == "Install OpenSpec"
        )
        self.assertIsNotNone(makefile)
        assert makefile is not None
        self.assertEqual(install["env"]["OPENSPEC_VERSION"], makefile.group(1))
        self.assertIn(
            f"@fission-ai/openspec@{makefile.group(1)}",
            (ROOT / "README.md").read_text(),
        )

    def test_every_capability_has_a_spec(self):
        for capability in sorted((ROOT / "openspec" / "specs").iterdir()):
            with self.subTest(capability=capability.name):
                text = (capability / "spec.md").read_text()
                self.assertIn("## Purpose", text)
                self.assertIn("### Requirement:", text)

    def test_claude_code_loads_the_agent_guide(self):
        self.assertEqual((ROOT / "CLAUDE.md").read_text().strip(), "@AGENTS.md")


if __name__ == "__main__":
    unittest.main()

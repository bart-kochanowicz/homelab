"""Check that the post-edit hook formats files and reports lint problems."""

import shutil
import tempfile
import unittest
from pathlib import Path

from .support import ROOT, run_hook


class CheckFileTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="homelab-hook-")
        self.addCleanup(directory.cleanup)
        self.project = Path(directory.name)
        # Like the repository, the project pins its tools: aqua shims (as in
        # CI) resolve terraform only below an aqua.yaml.
        for name in (".yamllint.yaml", "aqua.yaml"):
            shutil.copyfile(ROOT / name, self.project / name)

    def check(self, relative: str, content: str):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(path)},
            "cwd": str(self.project),
        }
        return run_hook("check_file.py", payload, self.project), path

    @unittest.skipUnless(shutil.which("yamllint"), "yamllint is not installed")
    def test_yaml_problems_are_reported_to_the_agent(self):
        result, _ = self.check("apps/demo/service.yaml", "a: 1\na: 2\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("duplication of key", result.stderr)

    @unittest.skipUnless(shutil.which("yamllint"), "yamllint is not installed")
    def test_valid_yaml_passes_quietly(self):
        result, _ = self.check("apps/demo/service.yaml", "a: 1\n")
        self.assertEqual((result.returncode, result.stderr), (0, ""))

    @unittest.skipUnless(shutil.which("terraform"), "terraform is not installed")
    def test_terraform_is_formatted_in_place(self):
        result, path = self.check(
            "terraform/demo/main.tf", 'locals {\n  a    = "b"\n}\n'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.read_text(), 'locals {\n  a = "b"\n}\n')

    @unittest.skipUnless(shutil.which("terraform"), "terraform is not installed")
    def test_backend_and_example_inputs_are_formatted_through_stdin(self):
        for relative in (
            "terraform/garage.s3.tfbackend",
            "terraform/demo/x.tfvars.example",
        ):
            with self.subTest(file=relative):
                result, path = self.check(relative, 'bucket    = "state"\n')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(path.read_text(), 'bucket = "state"\n')

    @unittest.skipUnless(shutil.which("uv"), "uv is not installed")
    def test_an_import_added_before_its_use_survives_the_edit(self):
        result, path = self.check("tests/demo/test_x.py", "import re\n\nx  =  1\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.read_text(), "import re\n\nx = 1\n")

    def test_invalid_json_is_reported(self):
        result, _ = self.check(".claude/settings.json", "{")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid JSON", result.stderr)

    def test_files_outside_the_project_are_ignored(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json") as outside:
            outside.write("{")
            outside.flush()
            payload = {"tool_name": "Write", "tool_input": {"file_path": outside.name}}
            result = run_hook("check_file.py", payload, self.project)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest

import yaml


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/terraform-dispatch.yaml"


class TerraformRunPollingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.functions = re.findall(
            r"          wait_for_run\(\) \{\n(.*?)\n          \}",
            WORKFLOW.read_text(),
            re.DOTALL,
        )
        if len(cls.functions) != 2:
            raise AssertionError("Both plan and apply must have their polling tested.")

    def check_polling(self, responses, succeeds, requests):
        for job, body in zip(("plan", "apply"), self.functions):
            with self.subTest(job=job), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                gh = root / "gh"
                gh.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''\
                    import json, os, sys
                    from pathlib import Path
                    assert sys.argv[1:3] == [
                        "api", "repos/bart-kochanowicz/homelab-automation/actions/runs/123"
                    ], "Only status reads may be retried."
                    counter = Path(os.environ["REQUEST_COUNT"])
                    count = int(counter.read_text()) if counter.exists() else 0
                    counter.write_text(str(count + 1))
                    responses = json.loads(os.environ["RESPONSES"])
                    response = responses[min(count, len(responses) - 1)]
                    if response in ("404", "invalid_json"):
                        print("HTTP 404" if response == "404" else "unexpected end of JSON input",
                              file=sys.stderr)
                        sys.exit(1)
                    print(response)
                '''))
                gh.chmod(0o700)
                sleep = root / "sleep"
                sleep.write_text("#!/bin/sh\nexit 0\n")
                sleep.chmod(0o700)
                counter = root / "count"
                env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                           REQUEST_COUNT=str(counter), RESPONSES=json.dumps(responses))
                function = "wait_for_run() {\n" + textwrap.dedent(body) + "\n}\nwait_for_run 123"
                result = subprocess.run(
                    ["bash", "-euo", "pipefail", "-c", function],
                    env=env, capture_output=True, text=True, timeout=5,
                )
                self.assertEqual(result.returncode == 0, succeeds, result.stderr)
                self.assertEqual(int(counter.read_text()), requests, result.stderr)

    def test_new_run_404_then_success(self):
        self.check_polling(["404", "pending", "success"], True, 3)

    def test_empty_json_response_then_success(self):
        self.check_polling(["invalid_json", "success"], True, 2)

    def test_persistent_api_error_stops_after_six_reads(self):
        self.check_polling(["404"], False, 6)

    def test_successful_read_resets_error_budget(self):
        self.check_polling(["404"] * 5 + ["pending"] + ["404"] * 5 + ["success"], True, 12)

    def test_failed_cancelled_or_timed_out_run_stops_immediately(self):
        for status in ("failure", "cancelled", "timed_out"):
            with self.subTest(status=status):
                self.check_polling([status], False, 1)


class TerraformRootDispatchTests(unittest.TestCase):
    def test_selected_roots_apply_only_their_saved_plans(self):
        workflow = yaml.safe_load(WORKFLOW.read_text())
        for selection, roots in (("crafty", ["crafty"]), ("unifi", ["unifi"]),
                                 ("cloudflare", ["cloudflare"]),
                                 ("all", ["cloudflare", "unifi", "crafty"])):
            with self.subTest(selection=selection), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                requests = root / "requests"
                output = root / "outputs"
                gh = root / "gh"
                gh.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''\
                    import json, os, sys
                    from pathlib import Path
                    args = sys.argv[1:]
                    if any(value.endswith("/dispatches") for value in args):
                        fields = dict(args[index + 1].split("=", 1)
                                      for index, value in enumerate(args) if value == "-f")
                        assert fields.pop("ref") == "main"
                        inputs = {key.removeprefix("inputs[").removesuffix("]"): value
                                  for key, value in fields.items()}
                        with Path(os.environ["REQUESTS"]).open("a") as log:
                            log.write(json.dumps(inputs) + "\\n")
                        print({"cloudflare": 101, "unifi": 102, "crafty": 103}[inputs["terraform_root"]])
                    elif any(value.endswith("/git/ref/heads/main") for value in args):
                        print(os.environ["SOURCE_SHA"])
                    elif any("/actions/runs/" in value for value in args):
                        print("success")
                    else:
                        raise SystemExit("Unexpected GitHub request")
                '''))
                gh.chmod(0o700)
                env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                           GH_TOKEN="test-only", SOURCE_SHA="a" * 40,
                           VALIDATION_RUN_ID="10", GITHUB_RUN_ID="20", ROOT=selection,
                           REQUESTS=str(requests), GITHUB_OUTPUT=str(output),
                           GITHUB_STEP_SUMMARY=str(root / "summary"))
                plan_step = workflow["jobs"]["plan"]["steps"][0]
                result = subprocess.run(["bash", "-euo", "pipefail", "-c", plan_step["run"]],
                                        env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                planned = [json.loads(line) for line in requests.read_text().splitlines()]
                self.assertEqual([item["terraform_root"] for item in planned], roots)
                for item in planned:
                    self.assertEqual(item["operation"], "plan")
                    self.assertEqual(item["source_sha"], env["SOURCE_SHA"])
                    self.assertEqual(item["validation_run_id"], "10")
                    self.assertEqual(item["approval_run_id"], "20")
                plan_outputs = dict(line.split("=", 1) for line in output.read_text().splitlines())
                apply_step = workflow["jobs"]["apply"]["steps"][0]
                for name, expression in apply_step["env"].items():
                    if name.endswith("_PLAN"):
                        match = re.fullmatch(r"\$\{\{ needs\.plan\.outputs\.(\w+) \}\}", expression)
                        self.assertIsNotNone(match)
                        field = match.group(1)
                        self.assertEqual(workflow["jobs"]["plan"]["outputs"][field],
                                         "${{ steps.plan.outputs." + field + " }}")
                        env[name] = plan_outputs.get(field, "")
                result = subprocess.run(["bash", "-euo", "pipefail", "-c", apply_step["run"]],
                                        env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                applied = [json.loads(line) for line in requests.read_text().splitlines()][len(roots):]
                self.assertEqual([item["terraform_root"] for item in applied], roots)
                for item in applied:
                    self.assertEqual(item["operation"], "apply")
                    self.assertEqual(item["plan_run_id"], plan_outputs[item["terraform_root"]])
                    self.assertEqual(item["source_sha"], env["SOURCE_SHA"])
                    self.assertEqual(item["validation_run_id"], "10")
                    self.assertEqual(item["approval_run_id"], "20")


if __name__ == "__main__":
    unittest.main()

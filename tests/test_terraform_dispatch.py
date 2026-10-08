import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest


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


if __name__ == "__main__":
    unittest.main()

from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "system/monitoring/alertmanager-email.tmpl"
ALERTS_URL = "https://grafana.thecavespace.net/alerting/groups?alertmanager=Alertmanager"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.urls.extend(value for key, value in attrs if key == "href")


class AlertEmailTemplateTests(unittest.TestCase):
    def render(self, name):
        data = {
            "receiver": "email",
            "status": "firing",
            "externalURL": "http://alertmanager.monitoring:9093",
            "alerts": [
                {
                    "status": status,
                    "labels": {"alertname": f"Example-{status}", "instance": "<worker&>"},
                    "annotations": {"summary": "<script>unsafe</script>", "description": "A & B"},
                    "generatorURL": "http://prometheus.monitoring:9090/graph",
                }
                for status in ("firing", "resolved")
            ],
        }
        with tempfile.TemporaryDirectory(prefix="alert-email-") as directory:
            fixture = Path(directory) / "alerts.json"
            fixture.write_text(json.dumps(data))
            result = subprocess.run(
                ["amtool", "template", "render", f"--template.glob={TEMPLATE}",
                 f'--template.text={{{{ template "{name}" . }}}}',
                 "--template.type=html", f"--template.data={fixture}"],
                capture_output=True, text=True, timeout=15,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        links = Links()
        links.feed(result.stdout)
        self.assertEqual(links.urls, [ALERTS_URL])
        self.assertNotIn(".monitoring:", result.stdout)
        return result.stdout

    def test_operational_email_links_and_alert_details(self):
        rendered = self.render("cavespace.email")
        self.assertIn("Example-firing - FIRING", rendered)
        self.assertIn("Example-resolved - RESOLVED", rendered)
        self.assertIn("&lt;worker&amp;&gt;", rendered)
        self.assertIn("&lt;script&gt;unsafe&lt;/script&gt;", rendered)
        self.assertIn("A &amp; B", rendered)
        self.assertNotIn("<script>", rendered)

    def test_delivery_check_links_to_the_external_alertmanager_in_grafana(self):
        self.assertIn("every seven days", self.render("cavespace.heartbeat"))

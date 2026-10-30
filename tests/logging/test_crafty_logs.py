import time
from datetime import datetime, timedelta, timezone

from .support import LOGGING, LoggingTestCase


class CraftyLogTests(LoggingTestCase):
    def test_real_crafty_lines_keep_event_times_and_multiline_failures(self):
        server = "pipeline-fixture"
        config = (LOGGING / "config.alloy").read_text()
        # Exercise the production file pipeline without Kubernetes discovery or game logs.
        config = (
            'loki.source.file "crafty" {'
            + config.split('loki.source.file "crafty" {', 1)[1]
        )
        config = (
            config.split('loki.source.file "minecraft" {', 1)[0]
            + 'loki.write "local" {'
            + config.split('loki.write "local" {', 1)[1]
        )
        config = config.replace(
            "http://loki.monitoring.svc:3100", "http://127.0.0.1:3100"
        )
        (self.path / "alloy.alloy").write_text(config)
        from zoneinfo import ZoneInfo

        stamp = datetime.now(timezone.utc) - timedelta(days=1)

        def line(instant: datetime, message: str) -> str:
            local = instant.astimezone(ZoneInfo("Europe/Warsaw")).strftime(
                "%Y-%m-%d %H:%M:%S,%f"
            )[:-3]
            return f"{local} - [Crafty] - INFO - app.classes.shared.backup_mgr - {message}\n"

        (self.path / "logs/commander.log").write_text(
            line(
                stamp - timedelta(days=20),
                "Failed to create backup of server old (ID fixture)",
            )
            + line(stamp, f"Backup of server: {server} completed")
            + line(
                stamp + timedelta(milliseconds=100),
                f"Failed to create backup of server {server} (ID fixture)",
            )
            + "Traceback (most recent call last):\n  OSError: fixture\n"
        )
        name = self.name + "-alloy"
        self.containers.append(name)
        self.command(
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--user",
            self.test_user,
            "--network",
            "container:" + self.name,
            "--cap-drop",
            "ALL",
            "-v",
            f"{self.path}/alloy.alloy:/etc/alloy/config.alloy:ro",
            "-v",
            f"{self.path}/logs:/var/log/crafty:ro",
            "-v",
            f"{self.path}/positions:/var/lib/alloy",
            self.images["alloy"],
            "run",
            "--storage.path=/var/lib/alloy",
            "/etc/alloy/config.alloy",
        )
        deadline = time.monotonic() + 30
        query = f'count_over_time({{source="file",server_name="{server}",backup_status="failure"}}[2d])'
        while time.monotonic() < deadline:
            if self.query(query):
                break
            time.sleep(1)
        else:
            self.fail(
                "Alloy did not deliver the failure: "
                + self.command("docker", "logs", name)
            )
        self.assertTrue(self.unhealthy(server))
        self.assertFalse(
            self.query('count_over_time({source="file",server_name="old"}[14d])')
        )
        self.assertFalse(
            self.query(f'count_over_time({{source="file",server_name="{server}"}}[1h])')
        )
        self.command("docker", "stop", name)
        self.assertTrue(self.unhealthy(server))

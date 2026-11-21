import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .support import ROOT, GatewayTestCase

CARD = "front-door-events-card.js"


class HomeAssistantGatewayTests(GatewayTestCase):
    def test_home_assistant_route_only_uses_its_private_home_listener_and_service(self):
        resources = self.rendered("apps-home-assistant.yaml")
        routes = [item for item in resources if item["kind"] == "HTTPRoute"]
        self.assertEqual(len(routes), 1)
        route = routes[0]
        self.assertEqual(route["metadata"]["namespace"], "home-assistant")
        spec = route["spec"]
        self.assertEqual(
            spec["parentRefs"],
            [
                {
                    "name": "private-home",
                    "namespace": "private-home",
                    "sectionName": "home-assistant",
                }
            ],
        )
        self.assertEqual(spec["hostnames"], ["ha.thecavespace.net"])
        self.assertEqual(len(spec["rules"]), 1)
        rule = spec["rules"][0]
        self.assertEqual(set(rule), {"matches", "backendRefs", "timeouts"})
        self.assertEqual(
            rule["matches"], [{"path": {"type": "PathPrefix", "value": "/"}}]
        )
        self.assertEqual(
            rule["backendRefs"], [{"name": "home-assistant", "port": 8123}]
        )
        self.assertEqual(rule["timeouts"], {"request": "0s"})
        service = next(
            item
            for item in resources
            if item["kind"] == "Service"
            and item["metadata"]["name"] == rule["backendRefs"][0]["name"]
        )
        self.assertEqual(
            service["metadata"]["namespace"], route["metadata"]["namespace"]
        )
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertIn(
            {"name": "https", "port": 8123, "targetPort": 8123, "protocol": "TCP"},
            service["spec"]["ports"],
        )

    def test_home_assistant_backend_tls_matches_the_mounted_certificate_and_probes(
        self,
    ):
        resources = self.rendered("apps-home-assistant.yaml")
        certificate = next(item for item in resources if item["kind"] == "Certificate")
        policy = next(item for item in resources if item["kind"] == "BackendTLSPolicy")
        service = next(item for item in resources if item["kind"] == "Service")
        deployment = next(item for item in resources if item["kind"] == "Deployment")
        self.assertEqual(
            policy["spec"]["targetRefs"],
            [
                {
                    "group": "",
                    "kind": "Service",
                    "name": service["metadata"]["name"],
                    "sectionName": service["spec"]["ports"][0]["name"],
                }
            ],
        )
        self.assertEqual(
            policy["spec"]["validation"],
            {
                "hostname": "ha.thecavespace.net",
                "wellKnownCACertificates": "System",
            },
        )
        self.assertEqual(
            set(certificate["spec"]["dnsNames"]),
            {
                policy["spec"]["validation"]["hostname"],
                "ha-backend.thecavespace.net",
            },
        )
        self.assertEqual(
            certificate["spec"]["issuerRef"]["name"], "letsencrypt-production"
        )
        self.assertEqual(certificate["spec"]["privateKey"]["rotationPolicy"], "Always")
        self.assertLess(
            int(certificate["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]),
            int(policy["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]),
        )
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]
        mount = next(
            item for item in container["volumeMounts"] if item["name"] == "backend-tls"
        )
        self.assertTrue(mount["readOnly"])
        self.assertFalse({"subPath", "subPathExpr"} & set(mount))
        volume = next(item for item in pod["volumes"] if item["name"] == mount["name"])
        secret = certificate["spec"]["secretName"]
        self.assertEqual(volume["secret"], {"secretName": secret, "defaultMode": 0o400})
        self.assertEqual(
            deployment["metadata"]["annotations"][
                "secret.reloader.stakater.com/reload"
            ],
            secret,
        )
        self.assertEqual(deployment["spec"]["strategy"], {"type": "Recreate"})
        for probe in ("livenessProbe", "readinessProbe"):
            self.assertEqual(container[probe]["httpGet"]["scheme"], "HTTPS")
            port = next(
                item
                for item in container["ports"]
                if item["name"] == container[probe]["httpGet"]["port"]
            )
            self.assertEqual(
                port["containerPort"], service["spec"]["ports"][0]["targetPort"]
            )
        http = self.main_configuration()["http"]
        self.assertEqual(http["ssl_certificate"], mount["mountPath"] + "/tls.crt")
        self.assertEqual(http["ssl_key"], mount["mountPath"] + "/tls.key")

    def test_home_assistant_host_access_requires_home_proxy_identity(self):
        policies = self.rendered("system-network-policies.yaml")
        host = next(
            item
            for item in policies
            if item["kind"] == "CiliumClusterwideNetworkPolicy"
            and item["metadata"]["name"] == "homelab-host-firewall"
        )
        proxy_rules = [
            rule
            for rule in host["spec"]["ingress"]
            if any(
                selector.get("matchLabels", {}).get("k8s:io.kubernetes.pod.namespace")
                == "private-home"
                for selector in rule.get("fromEndpoints", [])
            )
        ]
        self.assertEqual(len(proxy_rules), 1)
        rule = proxy_rules[0]
        self.assertEqual(set(rule), {"fromEndpoints", "toPorts"})
        self.assertEqual(
            rule["fromEndpoints"],
            [
                {
                    "matchLabels": {
                        "k8s:io.kubernetes.pod.namespace": "private-home",
                        "k8s:app.kubernetes.io/managed-by": "envoy-gateway",
                        "k8s:app.kubernetes.io/component": "proxy",
                        "k8s:gateway.envoyproxy.io/owning-gateway-name": "private-home",
                    }
                }
            ],
        )
        ports = [{"ports": [{"port": "8123", "protocol": "TCP"}]}]
        self.assertEqual(rule["toPorts"], ports)
        home = next(
            item
            for item in policies
            if item["kind"] == "CiliumNetworkPolicy"
            and item["metadata"]["name"] == "private-proxy"
            and item["metadata"]["namespace"] == "private-home"
        )
        self.assertEqual(
            home["spec"]["endpointSelector"],
            {
                "matchLabels": {
                    "app.kubernetes.io/managed-by": "envoy-gateway",
                    "app.kubernetes.io/component": "proxy",
                    "gateway.envoyproxy.io/owning-gateway-name": "private-home",
                }
            },
        )
        node_rules = [rule for rule in home["spec"]["egress"] if "toEntities" in rule]
        self.assertEqual(
            node_rules, [{"toEntities": ["host", "remote-node"], "toPorts": ports}]
        )

    @staticmethod
    def yaml_json(text: str) -> Any:
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as directory:
            fixture = Path(directory) / "fixture.yaml"
            fixture.write_text(text)
            result = subprocess.run(
                ["yq", "-o=json", ".", str(fixture)],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
        return json.loads(result.stdout)

    def main_configuration(self) -> dict[str, Any]:
        """The configuration.yaml owned by the platform, without the packages."""
        config = self.config_map("home-assistant-config")
        return self.yaml_json(config["data"]["configuration.yaml"])

    def packages(self) -> dict[str, dict[str, Any]]:
        return {
            Path(name).stem: self.yaml_json(text)
            for name, text in self.config_map("home-assistant-packages")["data"].items()
        }

    def front_door_configuration(self) -> dict[str, Any]:
        """The configuration that Home Assistant runs: the main file plus its packages.

        Home Assistant merges the keys of each package into the configuration; a key
        in both would be an error there, so it is one here.
        """
        configuration = self.main_configuration()
        for package in self.packages().values():
            for key, value in package.items():
                self.assertNotIn(key, configuration)
                configuration[key] = value
        return configuration

    def test_camera_snapshot_is_a_raw_jpeg_mqtt_image_on_a_topic_the_camera_may_write(
        self,
    ):
        configuration = self.front_door_configuration()
        self.assertEqual(
            configuration["mqtt"]["image"],
            [
                {
                    "name": "Front door camera snapshot",
                    "unique_id": "front_door_camera_snapshot",
                    "image_topic": "doorview/front-door-camera/snapshot",
                    "content_type": "image/jpeg",
                    "encoding": "",
                }
            ],
        )
        broker = next(
            item
            for item in self.rendered("apps-mosquitto.yaml")
            if item["kind"] == "ConfigMap"
        )
        self.assertIn(
            "topic write doorview/front-door-camera/#",
            broker["data"]["acl"].splitlines(),
        )
        self.assertIn("max_packet_size 524288", broker["data"]["mosquitto.conf"])
        # The snapshot needs no credentials, router rule or Secret of its own.
        text = json.dumps(configuration)
        self.assertNotIn("10.0.50.190", text)
        # The only shell command prunes the archive; nothing reaches the camera.
        self.assertEqual(
            set(configuration["shell_command"]), {"front_door_snapshot_cleanup"}
        )

    def front_door_automation(self, automation_id: str) -> dict[str, Any]:
        return next(
            item
            for item in self.front_door_configuration()["automation front_door"]
            if item["id"] == automation_id
        )

    def test_motion_automation_waits_for_a_fresh_snapshot_and_is_rate_limited(self):
        automation = self.front_door_automation("front_door_motion_notification")
        self.assertEqual(automation["mode"], "single")
        self.assertEqual(automation["max_exceeded"], "silent")
        self.assertEqual(
            automation["triggers"],
            [
                {
                    "trigger": "state",
                    "entity_id": "binary_sensor.front_door_camera_motion",
                    "from": "off",
                    "to": "on",
                }
            ],
        )
        image = "image.front_door_camera_snapshot"
        actions = automation["actions"]
        wait = actions[0]["then"][0]
        self.assertEqual(
            wait["wait_for_trigger"],
            # null ignores attribute changes such as the rotating access token.
            [{"trigger": "state", "entity_id": image, "to": None}],
        )
        self.assertEqual(wait["timeout"], "00:00:20")
        self.assertTrue(wait["continue_on_timeout"])
        choice = actions[2]["choose"][0]
        self.assertIn("snapshot_is_new", choice["conditions"])
        data = choice["sequence"][0]["data"]["data"]
        self.assertEqual(data["image"], f"/api/image_proxy/{image}")
        self.assertEqual(data["attachment"], {"url": f"/api/image_proxy/{image}"})
        # Both branches open the events dashboard: iOS reads url, Android clickAction.
        opens = {"url": "/front-door/events", "clickAction": "/front-door/events"}
        self.assertEqual({key: data[key] for key in opens}, opens)
        self.assertEqual(actions[2]["default"][0]["data"]["data"], opens)
        # The run holds the single slot for the cooldown, so repeated motion is dropped.
        self.assertEqual(actions[-1], {"delay": "00:01:00"})

    def test_notification_automation_does_not_depend_on_the_archive(self):
        automations = self.front_door_configuration()["automation front_door"]
        self.assertEqual(
            [item["id"] for item in automations],
            [
                "front_door_motion_notification",
                "front_door_snapshot_archive",
                "front_door_snapshot_retention",
            ],
        )
        notification = json.dumps(automations[0])
        self.assertNotIn("image.snapshot", notification)
        self.assertNotIn("shell_command", notification)

    def test_snapshots_are_archived_in_an_authenticated_media_directory(self):
        configuration = self.front_door_configuration()
        archive = "/config/media/front-door"
        self.assertEqual(
            configuration["homeassistant"]["media_dirs"], {"front_door": archive}
        )
        automation = self.front_door_automation("front_door_snapshot_archive")
        # The camera publishes snapshots retained, so Home Assistant sees the last
        # picture again after every restart or reconnect. Only a picture that follows
        # Motion turning on is saved: a replay is preceded by unavailable -> state.
        self.assertEqual(
            automation["triggers"],
            [
                {
                    "trigger": "state",
                    "entity_id": "binary_sensor.front_door_camera_motion",
                    "from": "off",
                    "to": "on",
                }
            ],
        )
        self.assertEqual(automation["mode"], "queued")
        image = "image.front_door_camera_snapshot"
        notification = self.front_door_automation("front_door_motion_notification")
        # Same freshness rule as the notification, so both act on the same picture.
        self.assertEqual(
            automation["variables"]["snapshot_is_new"],
            notification["variables"]["snapshot_is_new"],
        )
        wait = automation["actions"][0]["then"][0]
        self.assertEqual(
            wait["wait_for_trigger"],
            # null ignores attribute changes such as the rotating access token.
            [{"trigger": "state", "entity_id": image, "to": None}],
        )
        self.assertEqual(wait["timeout"], "00:00:20")
        self.assertTrue(wait["continue_on_timeout"])
        self.assertEqual(
            automation["actions"][1]["variables"]["snapshot_is_new"],
            automation["variables"]["snapshot_is_new"],
        )
        save = automation["actions"][2]
        self.assertEqual(save["if"], "{{ snapshot_is_new }}")
        self.assertEqual(len(save["then"]), 1)
        action = save["then"][0]
        self.assertEqual(action["action"], "image.snapshot")
        self.assertEqual(action["target"], {"entity_id": image})
        filename = action["data"]["filename"]
        self.assertTrue(filename.startswith(archive + "/"))
        # Named by the picture's own arrival time, not by the motion or the run.
        self.assertIn(f"states('{image}')", filename)
        self.assertIn("'%Y-%m-%d_%H-%M-%S'", filename)
        self.assertTrue(filename.endswith(".jpg"))
        # /local serves /config/www without authentication: no picture goes there, and
        # the only /local URL is the card's script.
        text = json.dumps(configuration)
        self.assertNotIn("/www", text)
        self.assertEqual(
            re.findall(r"/local[^\"]*", text),
            [f"/local/front-door/{CARD}?v={self.card_version()}"],
        )
        self.assertNotIn("allowlist_external_dirs", text)

    def test_archive_directory_exists_before_home_assistant_validates_media_dirs(self):
        deployment = next(
            item
            for item in self.rendered("apps-home-assistant.yaml")
            if item["kind"] == "Deployment"
        )
        pod = deployment["spec"]["template"]["spec"]
        init = pod["initContainers"][0]
        self.assertEqual(init["command"][:2], ["sh", "-c"])
        self.assertTrue(
            init["command"][2].startswith("mkdir -p /config/media/front-door && ")
        )
        self.assertIn("cp -n ", init["command"][2])
        self.assertIn({"name": "config", "mountPath": "/config"}, init["volumeMounts"])
        self.assertFalse(init["securityContext"]["allowPrivilegeEscalation"])
        self.assertTrue(init["securityContext"]["readOnlyRootFilesystem"])

    def run_cleanup(self, archive: Path) -> subprocess.CompletedProcess[str]:
        command = self.front_door_configuration()["shell_command"][
            "front_door_snapshot_cleanup"
        ]
        self.assertIn("retention_days=90;", command)
        self.assertEqual(command.count("/config/media/front-door"), 1)
        return subprocess.run(
            ["sh", "-c", command.replace("/config/media/front-door", str(archive))],
            capture_output=True,
            text=True,
            timeout=15,
        )

    @staticmethod
    def age(path: Path, seconds: float) -> None:
        modified = time.time() - seconds
        os.utime(path, (modified, modified))

    def test_retention_deletes_only_archive_snapshots_older_than_ninety_days(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as directory:
            root = Path(directory)
            archive = root / "front-door"
            archive.mkdir()
            outside = root / "outside.jpg"
            files = {
                "2026-08-01_10-00-00.jpg": 91 * 86400,
                "2026-08-23_10-00-00.jpg": 89 * 86400,
                "2026-11-12_10-00-00.jpg": 8 * 86400,
                "2026-11-20_10-00-00.jpg": 0,
                "notes.jpg": 120 * 86400,
                "2026-08-01_10-00-00.txt": 120 * 86400,
            }
            for name, age in files.items():
                path = archive / name
                path.write_bytes(b"jpeg")
                self.age(path, age)
            outside.write_bytes(b"jpeg")
            self.age(outside, 120 * 86400)
            (archive / "2026-07-01_10-00-00.jpg").symlink_to(outside)
            nested = archive / "nested"
            nested.mkdir()
            (nested / "2026-07-01_10-00-00.jpg").write_bytes(b"jpeg")
            self.age(nested / "2026-07-01_10-00-00.jpg", 120 * 86400)
            result = self.run_cleanup(archive)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                {path.name for path in archive.iterdir()},
                {
                    "2026-08-23_10-00-00.jpg",
                    "2026-11-12_10-00-00.jpg",
                    "2026-11-20_10-00-00.jpg",
                    "notes.jpg",
                    "2026-08-01_10-00-00.txt",
                    "2026-07-01_10-00-00.jpg",
                    "nested",
                },
            )
            self.assertTrue(outside.exists())
            self.assertTrue((nested / "2026-07-01_10-00-00.jpg").exists())

    def test_retention_succeeds_when_the_archive_is_empty_or_missing(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as directory:
            archive = Path(directory) / "front-door"
            self.assertEqual(self.run_cleanup(archive).returncode, 0)
            archive.mkdir()
            result = self.run_cleanup(archive)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(archive.iterdir()), [])

    def test_retention_runs_daily_and_at_startup_in_its_own_automation(self):
        automation = self.front_door_automation("front_door_snapshot_retention")
        self.assertEqual(
            automation["triggers"],
            [
                {"trigger": "time", "at": "04:15:00"},
                {"trigger": "homeassistant", "event": "start"},
            ],
        )
        self.assertEqual(
            automation["actions"],
            [{"action": "shell_command.front_door_snapshot_cleanup"}],
        )

    def test_archive_is_excluded_from_the_home_assistant_backup(self):
        values = json.loads(
            subprocess.run(
                ["yq", "-o=json", ".", str(ROOT / "system/backups/values.yaml")],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout
        )
        application = next(
            item
            for item in values["applications"]
            if item["pvc"] == "home-assistant-data-nvme"
        )
        self.assertEqual(application["excludePaths"], ["media/front-door"])

    def config_map(self, prefix: str) -> dict[str, Any]:
        return next(
            item
            for item in self.rendered("apps-home-assistant.yaml")
            if item["kind"] == "ConfigMap"
            and re.fullmatch(prefix + r"(-[0-9a-z]+)?", item["metadata"]["name"])
        )

    def card_source(self) -> str:
        return self.config_map("home-assistant-www-front-door")["data"][CARD]

    def card_version(self) -> str:
        return hashlib.sha256(self.card_source().encode()).hexdigest()[:16]

    def front_door_dashboard(self) -> dict[str, Any]:
        data = self.config_map("home-assistant-dashboards")["data"]
        return self.yaml_json(data["front-door.yaml"])

    def test_events_dashboard_is_declared_next_to_the_default_ui_dashboard(self):
        configuration = self.front_door_configuration()
        lovelace = configuration["lovelace"]
        # The default dashboard stays in the UI: only extra dashboards are declared.
        self.assertEqual(set(lovelace), {"dashboards"})
        self.assertEqual(set(lovelace["dashboards"]), {"front-door"})
        entry = lovelace["dashboards"]["front-door"]
        self.assertEqual(
            entry,
            {
                "mode": "yaml",
                "title": "Front door",
                "icon": "mdi:doorbell-video",
                "show_in_sidebar": True,
                "require_admin": False,
                "filename": "dashboards/front-door.yaml",
            },
        )
        # The URL path of a dashboard needs a hyphen.
        self.assertRegex(next(iter(lovelace["dashboards"])), r"^[a-z]+-[a-z-]+$")
        dashboard = self.front_door_dashboard()
        self.assertEqual([view["path"] for view in dashboard["views"]], ["events"])
        view = dashboard["views"][0]
        # A panel view holds exactly one card, which then spans the phone.
        self.assertTrue(view["panel"])
        self.assertEqual(len(view["cards"]), 1)
        card = view["cards"][0]
        self.assertEqual(card["type"], "custom:front-door-events-card")
        self.assertEqual(
            set(card), {"type", "page_size", "sources"}, "the card takes no other keys"
        )
        self.assertTrue(30 <= card["page_size"] <= 50)
        media_dirs = configuration["homeassistant"]["media_dirs"]
        for source in card["sources"]:
            self.assertEqual(set(source), {"label", "icon", "media_content_id"})
            match = re.fullmatch(
                r"media-source://media_source/([a-z_]+)", source["media_content_id"]
            )
            assert match, source
            self.assertIn(match.group(1), media_dirs)
        self.assertEqual([source["label"] for source in card["sources"]], ["Motion"])

    def test_notifications_open_the_dashboard_view(self):
        dashboards = self.front_door_configuration()["lovelace"]["dashboards"]
        view = self.front_door_dashboard()["views"][0]["path"]
        # Companion opens /<dashboard url path>/<view path>.
        path = f"/{next(iter(dashboards))}/{view}"
        self.assertEqual(path, "/front-door/events")
        notification = self.front_door_automation("front_door_motion_notification")
        text = json.dumps(notification)
        self.assertEqual(text.count(f'"url": "{path}"'), 2)
        self.assertEqual(text.count(f'"clickAction": "{path}"'), 2)

    def test_card_script_is_the_only_file_served_without_authentication(self):
        configuration = self.front_door_configuration()
        card = self.config_map("home-assistant-www-front-door")
        self.assertEqual(set(card["data"]), {CARD})
        self.assertEqual(
            configuration["frontend"],
            {"extra_module_url": [f"/local/front-door/{CARD}?v={self.card_version()}"]},
            "update ?v= to the start of the card's SHA-256 when the card changes",
        )
        deployment = next(
            item
            for item in self.rendered("apps-home-assistant.yaml")
            if item["kind"] == "Deployment"
        )
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]
        mounts = {item["name"]: item for item in container["volumeMounts"]}
        self.assertEqual(
            mounts["www-front-door"],
            {
                "name": "www-front-door",
                "mountPath": "/config/www/front-door",
                "readOnly": True,
            },
        )
        self.assertEqual(
            mounts["dashboards"],
            {
                "name": "dashboards",
                "mountPath": "/config/dashboards",
                "readOnly": True,
            },
        )
        # Nothing but the card's directory is mounted under /config/www, and the
        # archive is not under it.
        www = [
            item["mountPath"]
            for item in container["volumeMounts"]
            if item["mountPath"].startswith("/config/www")
        ]
        self.assertEqual(www, ["/config/www/front-door"])
        for source in configuration["homeassistant"]["media_dirs"].values():
            self.assertFalse(source.startswith("/config/www"))
        volumes = {item["name"]: item for item in pod["volumes"]}
        self.assertEqual(
            volumes["www-front-door"]["configMap"]["name"], card["metadata"]["name"]
        )
        dashboard = self.config_map("home-assistant-dashboards")
        self.assertEqual(set(dashboard["data"]), {"front-door.yaml"})
        self.assertEqual(
            volumes["dashboards"]["configMap"]["name"],
            dashboard["metadata"]["name"],
        )
        # The generated names carry a content hash, so a change rolls the pod.
        for name in (card, dashboard):
            self.assertRegex(name["metadata"]["name"], r"-[0-9a-z]{10}$")

    def test_card_reaches_pictures_only_through_signed_media_source_urls(self):
        source = self.card_source()
        # Authenticated mechanisms only: the listing and a signed URL per picture.
        self.assertIn('"media_source/browse_media"', source)
        self.assertIn('"media_source/resolve_media"', source)
        # No fixed picture path, no unauthenticated route, nothing from outside.
        forbidden = [
            r"/media/",
            r"/local",
            r"/api/image_proxy",
            r"/www",
            r"authSig",
            r"\bfetch\(",
            r"XMLHttpRequest",
            r"\bWebSocket\(",
            r"\bimport\b",
            r"innerHTML",
            r"\beval\(",
            r"localStorage",
            r"https?://",
        ]
        self.assertEqual(
            [pattern for pattern in forbidden if re.search(pattern, source)], []
        )

    def test_card_reads_the_archive_file_names(self):
        source = self.card_source()
        pattern = re.search(r"const NAME = /(.+)/;", source)
        assert pattern
        name = re.compile(pattern.group(1))
        self.assertTrue(name.fullmatch("2026-11-21_18-30-00.jpg"))
        for other in ("notes.jpg", "2026-11-21_18-30-00.png", "2026-11-21 18-30.jpg"):
            self.assertIsNone(name.fullmatch(other))
        # The archive names its files with the format that the card parses and that
        # the retention matches.
        archive = self.front_door_automation("front_door_snapshot_archive")
        self.assertIn(
            "'%Y-%m-%d_%H-%M-%S'", archive["actions"][2]["then"][0]["data"]["filename"]
        )
        cleanup = self.front_door_configuration()["shell_command"][
            "front_door_snapshot_cleanup"
        ]
        self.assertIn("'????-??-??_??-??-??.jpg'", cleanup)

    def test_platform_configuration_only_loads_the_content_directory(self):
        main = self.main_configuration()
        # The platform owns plumbing: the URLs, the media folder, the HTTP server and
        # the files that the UI edits. Cameras, automations and dashboards are packages.
        self.assertEqual(
            set(main),
            {
                "default_config",
                "homeassistant",
                "http",
                "automation ui",
                "script",
                "scene",
            },
        )
        self.assertEqual(main["homeassistant"]["packages"], "packages")
        packages = self.packages()
        self.assertEqual(set(packages), {"front_door"})
        self.assertEqual(
            set(packages["front_door"]),
            {
                "frontend",
                "lovelace",
                "mqtt",
                "shell_command",
                "automation front_door",
            },
        )
        # A package cannot hold `homeassistant`, so the media folder stays in the
        # main file; the package only refers to it.
        self.assertEqual(
            main["homeassistant"]["media_dirs"],
            {"front_door": "/config/media/front-door"},
        )

    def test_config_directory_mirrors_config_and_every_file_is_delivered(self):
        directory = ROOT / "apps/home-assistant"
        kustomization = self.yaml_json((directory / "kustomization.yaml").read_text())
        generators = kustomization["configMapGenerator"]
        listed = {file for item in generators for file in item["files"]}
        on_disk = {
            str(path.relative_to(directory))
            for path in (directory / "config").rglob("*")
            if path.is_file() and path.name != "README.md"
        }
        # A file that no generator lists would silently never reach the pod.
        self.assertEqual(listed, on_disk)
        deployment = next(
            item
            for item in self.rendered("apps-home-assistant.yaml")
            if item["kind"] == "Deployment"
        )
        pod = deployment["spec"]["template"]["spec"]
        mounts = {
            item["name"]: item["mountPath"]
            for item in pod["containers"][0]["volumeMounts"]
        }
        volumes = {item["name"]: item for item in pod["volumes"]}
        for generator in generators:
            folders = {str(Path(file).parent) for file in generator["files"]}
            self.assertEqual(len(folders), 1, "one ConfigMap per folder")
            folder = folders.pop()
            self.assertTrue(folder.startswith("config/"))
            volume = next(
                name
                for name, item in volumes.items()
                if re.fullmatch(
                    generator["name"] + r"-[0-9a-z]+",
                    item.get("configMap", {}).get("name", ""),
                )
            )
            # The folder is mounted at the same path under /config, read-only.
            self.assertEqual(
                mounts[volume], "/config/" + folder.removeprefix("config/")
            )

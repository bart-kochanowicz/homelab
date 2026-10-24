#!/usr/bin/env python3
"""A local Kubernetes state machine for backup failure and recovery tests."""
import copy
import json
import os
from pathlib import Path
import sys


path = Path(os.environ["TEST_CLUSTER_STATE"])
cluster = json.loads(path.read_text())
args = [arg for arg in sys.argv[1:] if not arg.startswith("--request-timeout=")]
namespace = args[args.index("-n") + 1]
args.remove("-n")
args.remove(namespace)
cluster["calls"].append([namespace, *args])


def respond(value=None, error=None):
    path.write_text(json.dumps(cluster))
    if error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
    if value is not None:
        print(value if isinstance(value, str) else json.dumps(value))
    raise SystemExit(0)


action, resource = args[:2]
name = args[2] if len(args) > 2 else None
faults = cluster["faults"]
if action == "get" and resource == "appproject":
    project = copy.deepcopy(cluster["projects"][name])
    if faults.get("missing_window") == name:
        project["spec"]["syncWindows"] = []
    respond(project)
if action == "get" and resource == "application":
    app = copy.deepcopy(cluster["applications"][name])
    if faults.get("active_application") == name:
        app["operation"] = {"sync": {}}
        app["status"]["operationState"] = {"phase": "Running"}
    respond(app)
if action == "get" and resource == "pod":
    if faults.get("forbidden_helper") == namespace:
        respond(error="Forbidden: helper read denied")
    respond(cluster["helpers"][namespace])
if action == "get" and resource == "pvc":
    respond({"status": {"phase": "Bound"}})
if action == "get" and resource == "deployment":
    deployment = cluster["deployments"][namespace]
    if name != deployment["name"]:
        respond(error="Unexpected deployment")
    replicas = deployment["replicas"]
    if any(arg.startswith("jsonpath=") for arg in args):
        respond(str(replicas))
    respond({"metadata": {"generation": 1}, "spec": {"replicas": replicas},
             "status": {"observedGeneration": 1, "readyReplicas": replicas,
                        "availableReplicas": replicas}})
if action == "scale" and resource == "deployment":
    deployment = cluster["deployments"][namespace]
    replicas = int(next(arg.split("=", 1)[1] for arg in args
                        if arg.startswith("--replicas=")))
    expected = int(next(arg.split("=", 1)[1] for arg in args
                        if arg.startswith("--current-replicas=")))
    if expected != deployment["replicas"]:
        respond(error="Replica precondition failed")
    if replicas > 0 and faults.get("restart_failure") == namespace:
        respond(error="Simulated API failure while restarting")
    deployment["replicas"] = replicas
    respond()
if action == "get" and resource == "pods":
    deployment = cluster["deployments"][namespace]
    items = [cluster["helpers"][namespace]]
    if deployment["replicas"] or faults.get("extra_writer") == namespace:
        items.append({"metadata": {"uid": "writer-" + namespace},
                      "status": {"phase": "Running"},
                      "spec": {"volumes": [{"persistentVolumeClaim": {
                          "claimName": deployment["pvc"]}}]}})
    respond({"items": items})
if action == "exec" and resource == "pvc-backup":
    path.write_text(json.dumps(cluster))
    command = args[args.index("--") + 1:]
    if faults.get("producer_failure") == namespace:
        sys.stdout.buffer.write(b"interrupted archive")
        raise SystemExit(7)
    command[command.index("/data")] = str(Path(os.environ["TEST_DATA_ROOT"]) / namespace)
    os.execvp(command[0], command)
if action == "patch" and resource == "lease":
    cluster["leases"][name] = json.loads(args[args.index("-p") + 1])["spec"]
    respond()
respond(error="Unexpected kubectl call: " + repr(args))

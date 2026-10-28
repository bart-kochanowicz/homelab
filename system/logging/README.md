# Logs

Loki stores application logs for 14 days on a 20 GiB NVMe PVC. The local-path
request is not a hard disk quota. Logs are disposable; no backup is scheduled.
Filesystem lookback matches retention so imported historical events are queryable immediately.
Loki has no public route. Network policies allow Alloy, Grafana, Prometheus and Houston.

Alloy reads Kubernetes container logs through the API and mounts Crafty/Minecraft
log directories read-only. Its separate 1 GiB PVC stores file positions.
Delivery retries use memory; this is not an audit log with guaranteed delivery.
Alloy has no Secret-read, exec or filesystem-write access to Crafty.
Houston's Alloy service reads journald with the `adm`/`systemd-journal` groups;
its binary and cursor state live on Houston's SSD. Local journald keeps its
100 MiB/seven-day bounds. Talos forwards service and kernel JSON over private TCP.
Its raw receiver requires Alloy's experimental stability flag; versions are pinned.

| Source | Private worker endpoint |
| --- | --- |
| Houston journal | `10.0.70.12:30514` (Loki HTTP) |
| Talos control plane | `10.0.70.12:30515` (JSON TCP) |
| Talos worker | `10.0.70.12:30516` (JSON TCP) |

These ports have no WAN forwarding. Source-preserving services and Cilium policies
restrict them to Houston or the cluster nodes. Transport stays within Servers VLAN70.

In Grafana, open **Explore → Loki** and select `namespace` or `service_name`.
The datasource and alert rules are managed in Git.

`MinecraftBackupUnhealthy` alerts after a failed copy without a later success, or
after eight days without success. Event timestamps come from Crafty logs, not
collector startup. The freshness matcher and game-log mount target the current
ATM10 server; update both when replacing it. A completion log does not replace a ZIP restore test.
`CraftyBackupStartFailed` reports startup errors seen in the last 15 minutes.
Delivery failures and Loki rule-evaluation errors alert separately through Prometheus.

Run `make validate`; Docker is needed for native Loki/Alloy integration tests.

After syncing logging and network policies, install Houston's collector:

```bash
ANSIBLE_CONFIG=infra/ansible/ansible.cfg ansible-playbook \
  infra/ansible/playbooks/houston.yml --tags alloy --ask-become-pass
talosctl -n 10.0.70.11 patch machineconfig --mode=no-reboot --patch @talos/patches/logging-control-plane.yaml
talosctl -n 10.0.70.12 patch machineconfig --mode=no-reboot --patch @talos/patches/logging-worker.yaml
```

Talos patch previews can include machine secrets; capture diagnostics only in ignored private files.

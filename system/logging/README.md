# Logs

Loki stores application logs for 14 days on a 20 GiB NVMe PVC. The local-path
request is not a hard disk quota. Logs are disposable; no backup is scheduled.
Filesystem lookback matches retention so imported historical events are queryable immediately.
Loki has no public route. Network policies allow only Alloy, Grafana and Prometheus.

Alloy reads Kubernetes container logs through the API and mounts Crafty/Minecraft
log directories read-only. Its separate 1 GiB PVC stores file positions.
Delivery retries use memory; this is not an audit log with guaranteed delivery.
Alloy has no Secret-read, exec or filesystem-write access to Crafty.
Houston/Talos system logs remain on their hosts.

In Grafana, open **Explore → Loki** and select `namespace` or `service_name`.
The datasource and alert rules are managed in Git.

`MinecraftBackupUnhealthy` alerts after a failed copy without a later success, or
after eight days without success. Event timestamps come from Crafty logs, not
collector startup. The freshness matcher and game-log mount target the current
ATM10 server; update both when replacing it. A completion log does not replace a ZIP restore test.
`CraftyBackupStartFailed` reports startup errors seen in the last 15 minutes.
Delivery failures and Loki rule-evaluation errors alert separately through Prometheus.

Run `make validate`; Docker is needed for native Loki/Alloy integration tests.

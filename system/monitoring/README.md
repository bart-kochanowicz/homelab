# Monitoring

## Dashboards

The `Homelab` folder contains Overview (readiness, GitOps, certificates and backup
age), Resources (CPU, memory, requests, restarts and data disks), and Network
(Cilium, Hubble and private gateway replicas). JSON files live in `dashboards/`;
Kustomize packages them into a ConfigMap watched by Grafana's existing sidecar.
Edit these files and merge through GitOps. Provisioned dashboards are read-only;
export a UI copy as JSON to bring changes back into the repository. Chart-provided
Kubernetes dashboards remain available alongside them.

## Alerts

Talos scheduler/controller-manager metrics listen on loopback. Their custom alerts
check pod readiness on each control-plane node, not component internals. Node
request alerts warn above 90% allocatable CPU or memory for 15 minutes; cluster-wide
N+1 overcommit alerts are disabled because local-path workloads cannot fail over.
Existing node pressure, filesystem, pod and Prometheus alerts remain enabled.

Unexpected Cilium drops alert above 1 packet/second per reason for 10 minutes.
Policy denials, load-balancer source rejection and unsupported L2/L3 protocols are
visible on the Network dashboard but do not send emails. Cilium and ArgoCD use
PodMonitors; missing scrapes alert separately. Backup age comes from completed
K8up Backup resources for Home Assistant, n8n, Grafana and the Crafty panel.
Failures and stalled preparation alert separately; a success older
than 36 hours warns that a daily schedule was missed. The weekly Crafty panel
backup warns after eight days; its failures use the same alerts. Job completion
measures backup execution; isolated restore tests remain a separate operational check.
K8up status is scraped from Kubernetes; its Pushgateway output is disabled.

Run `make validate-monitoring` to render monitoring and test rules with the pinned
`promtool`. Full repository validation also runs these tests.

## Email notifications

Alertmanager uses Brevo SMTP with verified STARTTLS. Recipient addresses and SMTP
credentials are stored together in the `alertmanager-email` SealedSecret.
Operational alerts include recovery notifications. Watchdog sends a separate
delivery check every seven days; ten-day notification retention preserves that interval.
Email links open Grafana alert groups using the provisioned `Alertmanager` data source.

Edit the ignored `.secrets/alertmanager-email.yaml`, validate it with the matching
Alertmanager version's `amtool check-config`, then regenerate from the repository root:

```bash
kubectl create secret generic alertmanager-email -n monitoring --dry-run=client \
  --from-file=alertmanager.yaml=.secrets/alertmanager-email.yaml \
  --from-file=email.tmpl=system/monitoring/alertmanager-email.tmpl -o json |
  kubeseal --controller-name=sealed-secrets-controller \
    --controller-namespace=sealed-secrets --format=yaml |
  yq 'del(.metadata.creationTimestamp, .spec.template.metadata.creationTimestamp) |
    .metadata.annotations."argocd.argoproj.io/sync-wave" = "-1"' \
    > system/monitoring/alertmanager-email-sealed-secret.yaml
```

Keep the local file mode `600`. Brevo deactivates SMTP keys after 90 days without
a successful send, even when no expiration date is set.

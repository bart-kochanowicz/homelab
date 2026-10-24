# Email notifications

Alertmanager uses Brevo SMTP with verified STARTTLS. Recipient addresses and SMTP
credentials are stored together in the `alertmanager-email` SealedSecret.
Operational alerts include recovery notifications. Watchdog sends a separate
delivery check every seven days; ten-day notification retention preserves that interval.

Edit the ignored `.secrets/alertmanager-email.yaml`, validate it with the matching
Alertmanager version's `amtool check-config`, then regenerate from the repository root:

```bash
kubectl create secret generic alertmanager-email -n monitoring --dry-run=client \
  --from-file=alertmanager.yaml=.secrets/alertmanager-email.yaml -o json |
  kubeseal --controller-name=sealed-secrets-controller \
    --controller-namespace=sealed-secrets --format=yaml |
  yq 'del(.metadata.creationTimestamp, .spec.template.metadata.creationTimestamp) |
    .metadata.annotations."argocd.argoproj.io/sync-wave" = "-1"' \
    > system/monitoring/alertmanager-email-sealed-secret.yaml
```

Keep the local file mode `600`. Brevo deactivates SMTP keys after 90 days without
a successful send, even when no expiration date is set.

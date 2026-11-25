# Sealed Secrets Web

The web interface seals Kubernetes Secrets for Git using the existing controller.
It cannot read existing Secrets. Its ServiceAccount can only read the controller
Service and proxy requests to that Service for its certificate and validation.
It does not manage resources in the cluster or commit files to Git.

Open <https://sealed-secrets.thecavespace.net> from the admin LAN or VPN. The
private-admin gateway restricts source addresses; the UI itself has no login.
Do not expose it publicly or use it from an untrusted admin/VPN device. The
gateway and backend proxy both use verified TLS; the backend proxy watches the
mounted certificate for rotation. Avoid sharing the screen or leaving plaintext
in the browser or clipboard.

Manually sync `network-policies` before deploying the UI; `argocd-bootstrap`
applies changes to `system/argocd/` automatically after merge. Review and apply the UniFi
Terraform plan for the private DNS record. Without it, the hostname will not
resolve through UniFi DNS.

Enter a Kubernetes Secret in the left editor with its exact `metadata.name`,
`metadata.namespace`, type, and keys under `stringData`, then click **Seal**.
Copy only the `Sealed Secret` output on the right into the relevant tracked YAML
file. Verify it contains `encryptedData` and no `stringData` or plaintext. Do not
save or commit the left-hand input. The default strict scope binds ciphertext to
both the Secret name and namespace. Commit the result and let ArgoCD synchronize.

When replacing an existing SealedSecret, preserve its annotations, labels, type,
all keys, and Secret template metadata. In particular, preserve both patch
annotations on `argocd-secret` and the sync-wave annotation on
`alertmanager-email`; see the [security runbook](../../docs/security-runbook.md)
and [monitoring guide](../monitoring/README.md). The UI does not retrieve existing
plaintext: supply all values again when regenerating a multi-key Secret.

The controller's public certificate is cached when the UI starts. Restart the UI
after controller key changes to use its current certificate. Controller key
backup and recovery remain separate; see the
[recovery guide](../../docs/sealed-secrets-recovery.md).

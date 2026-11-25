# webOS Developer Mode

The CronJob calls the LG API once a day at 03:00 in the Kubernetes
controller's time zone. The TV can be off. The client verifies the renewed
session; Kubernetes retries failures up to three times. Prometheus alerts on a
failed scheduled Job or 48 hours without a successful renewal. Renewal depends
on LG API availability and a valid session token.
The upstream 0.0.1 image has known critical vulnerabilities; review the image
scan and update the pinned image when a fixed release is available.

## Token setup and replacement

Enable Developer Mode and Key Server on the TV and configure the webOS CLI
connection as described in the [upstream guide](https://github.com/gabe565/webos-dev-mode#usage).
With the TV on, retrieve the `sessionToken` from the TV using
`ares-novacom --run 'cat /var/luna/preferences/devmode_enabled; echo'`.
Treat its output as a password; do not share it or put it in shell history.
If `ares-novacom --getkey` succeeds but commands fail with "All configured
authentication methods failed", decrypt a temporary copy of the fetched key with
`ssh-keygen -p` and read the file with OpenSSH on port `9922` as `prisoner`,
adding `-o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa`.
Delete the decrypted copy afterwards.

Use [Sealed Secrets Web](../../system/sealed-secrets-web/README.md) to seal the
`WEBOS_TOKEN` key for Secret `webos-dev-mode-token` in namespace `webos-dev-mode`.
`kubeseal --controller-namespace sealed-secrets --controller-name
sealed-secrets-controller` produces the same result from a dry-run Secret.
Save it to `apps/webos-dev-mode/sealed-secret.yaml`, which this directory's
`kustomization.yaml` lists, then commit and merge; ArgoCD deploys the encrypted
secret and the controller creates the Secret. For a replacement token,
regenerate the same file and commit it. If the session has
expired or LG rejects the token, re-enable Developer Mode on the TV, obtain the
new token, and repeat these steps. Reinstall removed sideloaded apps if needed.
Changes to the ArgoCD project under `system/argocd/` require a bootstrap or
manual ArgoCD sync before the new application can be deployed.

## Operations

List executions and view the logs of a specific Job:

```bash
kubectl -n webos-dev-mode get cronjob,job,pod
kubectl -n webos-dev-mode logs job/<job-name> --all-containers=true
kubectl -n webos-dev-mode describe job <job-name>
```

For a one-off session check, create a Job from the CronJob with the safe `check`
command and inspect its logs:

```bash
kubectl -n webos-dev-mode create job webos-dev-mode-check \
  --from=cronjob/webos-dev-mode --dry-run=client -o json |
  jq 'del(.metadata.ownerReferences) | .spec.template.spec.containers[0].args[2] = "check"' |
  kubectl -n webos-dev-mode create -f -
kubectl -n webos-dev-mode logs -f job/webos-dev-mode-check
```

The check Job has no CronJob owner, so it cannot count as a successful renewal.
Delete it after inspection before reusing its name.
The CLI's raw errors can include the token in a URL, so the wrapper suppresses
them and reports a generic failure. Inspect Job events, network connectivity,
LG API availability and token validity when troubleshooting.

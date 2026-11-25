---
name: seal-secret
description: Create, rotate or replace a SealedSecret for a Kubernetes credential without the agent seeing the plaintext. Use when a workload needs a new password, token or key, when a credential is rotated, or when a SealedSecret must be regenerated after a key change.
---

# SealedSecrets

Kubernetes credentials are committed only as strict-scope SealedSecrets,
bound to their name and namespace. The plaintext stays with the user: the
agent writes the Secret's shape, the user supplies values and seals them.

## Prepare

1. Find the consumer (`envFrom`, `secretKeyRef`, volume) and list the exact
   `metadata.name`, `metadata.namespace`, `type` and keys it reads.
2. When replacing an existing SealedSecret, read it and keep its annotations,
   labels, type, every key and `spec.template` metadata. The UI cannot read
   old values: the user re-enters every key of a multi-key Secret.
   `argocd-secret` keeps both patch annotations; `alertmanager-email` keeps its
   sync-wave annotation.

## Seal

Ask the user to seal; offer both ways and show the Secret skeleton with
placeholder values:

- **Sealed Secrets Web** at <https://sealed-secrets.thecavespace.net> (Admin
  LAN or VPN). Paste the Secret with `stringData`, click **Seal**, copy only the
  right-hand output.
- **kubeseal** (pinned in `aqua.yaml`), run by the user in their own terminal:

  ```bash
  kubeseal --controller-namespace sealed-secrets --format yaml \
    < secret.yaml > apps/<app>/sealed-secret.yaml && rm secret.yaml
  ```

The user writes the result to the tracked path, or pastes it to you. Never
ask for plaintext values in chat, and never write a `kind: Secret` file; the
guard hook blocks it.

## Check

1. The file has `kind: SealedSecret`, `encryptedData` and no `stringData`
   or `data`.
2. Add a new path to the SealedSecret allowlist in `.gitleaks.toml`.
3. Reference the file from the directory's `kustomization.yaml`.
4. Run `make validate-kustomize validate-security` (rendered manifests,
   config scans and gitleaks), then `make validate`.

After merge, ArgoCD syncs the SealedSecret. Restart consumers that read the
Secret only at startup unless a reloader watches it. Controller key backup
and recovery are in `docs/sealed-secrets-recovery.md`.

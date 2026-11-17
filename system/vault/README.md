# Vault

One manually unsealed Vault server uses Raft on the worker's retained local NVMe.
It has no failover. Do not initialize it until independent recovery and backup
procedures are ready. The Vault Application and network policies require manual
sync; create the protected namespace and policies before syncing Vault.

The UI is at `https://vault.thecavespace.net` from Admin and WireGuard. The
gateway and Vault listener use cert-manager's Let's Encrypt certificates. Private
DNS is managed by Terraform and requires a reviewed plan before apply.

Check the active context and the pod without exposing a network endpoint:

```bash
kubectl config current-context
kubectl -n vault get pods,pvc,certificate
kubectl -n vault port-forward pod/vault-0 8200:8200
```

For CLI access over the tunnel, set `VAULT_ADDR=https://127.0.0.1:8200` and
`VAULT_TLS_SERVER_NAME=vault.thecavespace.net`; use the system trust store.
In-cluster clients connecting to `vault.vault.svc` must also verify the listener
as `vault.thecavespace.net`. The certificate reloads without a Vault restart.
After a restart, manually unseal the existing server with two different shares:

```bash
kubectl -n vault exec -it vault-0 -- env \
  VAULT_TLS_SERVER_NAME=vault.thecavespace.net vault operator unseal
```

Never initialize it again. Preserve the namespace, volumes and unseal shares
during recovery or rollback.

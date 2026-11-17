# Vault

One manually unsealed Vault server uses Raft on the worker's retained local NVMe.
It has no failover. Do not initialize it until independent recovery and backup
procedures are ready. The Vault Application and network policies require manual
sync; create the protected namespace and policies before syncing Vault.

The UI is at `https://vault.thecavespace.net` from Admin and WireGuard. The
private gateway validates Vault's listener using `vault-backend-ca`; update that
public CA bundle when rotating the internal issuer, before changing the issuer.
Private DNS is managed by Terraform and requires a reviewed plan before apply.
After merging changes, sync `network-policies`, `vault`, then `gateways`; verify
the BackendTLSPolicy and route are accepted before applying the DNS plan.

Check the active context and the pod without exposing a network endpoint:

```bash
kubectl config current-context
kubectl -n vault get pods,pvc,certificate
kubectl -n vault port-forward pod/vault-0 8200:8200
```

For CLI access, trust the internal CA and set `VAULT_ADDR=https://127.0.0.1:8200`
and `VAULT_TLS_SERVER_NAME=vault.vault.svc`. A restarted server must be manually
unsealed; never initialize an existing server again. Preserve the namespace,
volumes, CA recovery materials and unseal shares during recovery or rollback.

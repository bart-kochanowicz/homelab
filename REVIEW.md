# Review policy

Reviews of this repository, human or agent, look for these in order. Report
each finding with `path:line`, the defect and the scenario that breaks.

## Blocking

1. **Exposure.** A hostname, Service, route, firewall rule or DNS record makes
   an endpoint reachable from the internet, or widens a source range beyond
   what the workload needs. Cloudflare Tunnel routes for applications are
   always blocking.
2. **Secrets.** Plaintext credentials, a `Secret` with `data`/`stringData`,
   state, plans, `.tfvars` or Talos configs in the diff. A SealedSecret that
   drops keys, annotations or template metadata it had before.
3. **Data loss.** Removed `Prune=false,Delete=false` on namespaces or PVCs,
   PVC or StorageClass changes that recreate volumes, backup sources dropped
   from `system/backups/values.yaml`, changed restic passwords, Terraform
   destroys or replacements the change does not explain.
4. **Network policy.** Allow rules broader than the peers and ports the
   workload uses, or a missing default-deny in a new namespace.
5. **Supply chain.** Images without a tag and digest, unpinned GitHub Actions,
   deleted lock files, tool versions outside `aqua.yaml`.
6. **Recovery.** Changes that weaken backup checks, freshness alerts or the
   documented restore and recovery procedures.

## Required with the change

- Tests for new behavior: networking tests for policies and routes, Terraform
  tests for UniFi changes, promtool fixtures for alert rules.
- Operational docs updated where the change alters a command or procedure.
- An updated spec in `openspec/specs/` when a guarantee changes, and no
  unarchived change folder left in `openspec/changes/`.
- The manual deployment steps named in the PR: syncs, bootstrap, Terraform
  plan, Ansible run.

## Out of scope

Lock files (`uv.lock`, `Chart.lock`, `.terraform.lock.hcl`) and vendored or
generated skills are reviewed only for provenance. Report at most five style
nits, after all other findings.

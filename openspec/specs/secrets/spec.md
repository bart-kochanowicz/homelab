# secrets Specification

## Purpose
Credentials never enter Git in plaintext. Kubernetes credentials are committed
as SealedSecrets; every other secret stays in ignored local files or private
GitHub Actions secrets.

## Requirements
### Requirement: Sealed Kubernetes credentials
Kubernetes Secrets in Git SHALL be SealedSecrets with strict scope, bound to
their name and namespace.

#### Scenario: New credential
- **WHEN** a workload needs a new credential
- **THEN** the repository gains a SealedSecret with `encryptedData` only
- **AND** no `Secret` with `data` or `stringData` is committed

### Requirement: Untracked private material
Terraform state and plans, `.tfvars` files, generated Talos configurations,
`.secrets/` and device backups SHALL stay out of Git.

#### Scenario: Local input in a worktree
- **WHEN** a worktree needs `terraform.tfvars` or `.secrets/`
- **THEN** it links the main checkout's ignored copy listed in `.worktreeinclude`

### Requirement: Secret detection
Validation SHALL scan the repository and its history for secrets, allowing
only SealedSecret ciphertext in listed files.

#### Scenario: Plaintext token committed
- **WHEN** a change contains a credential outside an allowlisted SealedSecret
- **THEN** `make validate` fails

### Requirement: Recoverable sealing keys
The SealedSecrets controller keys SHALL have a recovery copy outside the cluster.

#### Scenario: Controller reinstalled
- **WHEN** the cluster is rebuilt
- **THEN** restoring the saved keys lets the controller decrypt the committed SealedSecrets

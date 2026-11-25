# terraform-state Specification

## Purpose
Terraform manages UniFi, Cloudflare and Crafty from separate roots with remote
state in Garage. Changes reach infrastructure only through a reviewed plan.

## Requirements
### Requirement: Separate roots with remote state
Each deployable root SHALL live in `terraform/<name>/` with its own Garage
state key; reusable modules SHALL live in `terraform/modules/` without backends.

#### Scenario: New root
- **WHEN** a change adds Terraform configuration directly in `terraform/`
- **THEN** `make validate` fails

### Requirement: Reviewed applies
Infrastructure changes SHALL be applied only from a saved plan that an
operator reviewed and approved in GitHub Actions.

#### Scenario: Change merges
- **WHEN** a Terraform change merges and validation passes
- **THEN** Houston creates a plan, and nothing is applied until an operator approves that plan

#### Scenario: Local session
- **WHEN** an operator runs Terraform locally
- **THEN** it uses read-only Garage access and can plan but not apply

### Requirement: Serialized operations
Terraform operations SHALL hold Houston's shared lock, because Garage has no
native S3 locking.

#### Scenario: Concurrent plan
- **WHEN** a local plan session is open
- **THEN** an automation run waits for the lock

### Requirement: Pinned providers
Provider lock files SHALL be tracked, and validation SHALL initialize roots
with `-lockfile=readonly`.

#### Scenario: Provider drift
- **WHEN** a provider version differs from the lock file
- **THEN** initialization fails instead of updating the lock

### Requirement: State backups
Terraform state SHALL be backed up to private Cloudflare R2 storage with a
tested restore.

#### Scenario: Lost Garage state
- **WHEN** Houston's state is lost
- **THEN** state can be restored from R2 following `terraform/R2_BACKUP.md`

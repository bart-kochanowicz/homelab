# application-backups Specification

## Purpose
Stateful applications are backed up to encrypted restic repositories on
Houston while they keep running, and missing backups raise alerts.

## Requirements
### Requirement: Scheduled backups
Each application listed in `system/backups/values.yaml` SHALL have a K8up
schedule writing to its own restic repository on Houston, named after its
namespace.

#### Scenario: Scheduled backup
- **WHEN** an application's schedule runs
- **THEN** a snapshot with its SQLite database copies and a `files.tar` archive of the remaining files reaches Houston
- **AND** the application keeps running

### Requirement: Consistent databases
Backups SHALL copy each listed SQLite database through SQLite's online backup
API, and fail when a listed database is missing or the copy fails.

#### Scenario: Missing database
- **WHEN** a database listed for an application does not exist
- **THEN** preparation fails instead of producing a partial snapshot

### Requirement: Isolated credentials
Each repository SHALL have its own HTTP credentials and encryption password,
delivered to its namespace as a SealedSecret.

#### Scenario: Compromised namespace
- **WHEN** one namespace's backup credentials leak
- **THEN** they grant no access to another application's repository

### Requirement: Backup freshness alerts
Monitoring SHALL alert when an application's last successful backup is older
than its schedule allows.

#### Scenario: Backup stops running
- **WHEN** no backup succeeds within the alert window
- **THEN** Alertmanager sends an alert naming the namespace

### Requirement: Verified restores
Restores SHALL be tested in isolation before replacing live data; in-place
restores require explicit operator confirmation.

#### Scenario: Restore request
- **WHEN** an operator restores application data
- **THEN** the procedure in `docs/backups.md` restores to an isolated target first

# Houston

`houston-01` is a Debian 13 Dell Wyse 3040 used for Terraform operations.
Debian boots from eMMC; workloads use the ext4 SSD labelled `houston-data`
at `/srv/terraform`.

| Role | Managed state |
| --- | --- |
| `common` | Warsaw timezone, NTP, unattended security updates, bounded journald storage. |
| `storage` | SSD mount by verified UUID and scheduled TRIM. |
| `garage` | Garage 2.4.1, single-node `terraform-state` bucket and S3 key. |
| `terraform_cli` | Terraform 1.16.4, shared process lock, operator workspace and backup tools. |
| `github_runner` | Runner 2.337.0 for the private automation repository and systemd service. |

## Apply configuration

Run from the controller. Its `houston-01` SSH alias provides the address and
key; inventory selects `capcom`. The playbook validates the SSD label,
filesystem and mounted UUID before every role; it does not format disks.

```bash
cd infra/ansible
ansible-galaxy collection install -r requirements.yml
ansible-playbook playbooks/houston.yml --syntax-check
ansible-playbook playbooks/houston.yml --check --diff --ask-become-pass
ansible-playbook playbooks/houston.yml --ask-become-pass
```

Tags: `common`, `storage`, `garage`, `terraform_cli`, `github_runner`.
`--tags always` runs only the SSD preflight. Fresh-host check mode skips
operations needing downloaded binaries or generated secrets. Subsequent
applies should report `changed=0`. Open a new SSH session after group changes;
apply runner service changes while it is idle.

## Garage

Garage runs as `garage-svc` with config at `/etc/garage.toml` and data under
`/srv/terraform/garage`. S3 and RPC listen on `127.0.0.1:3900` and
`127.0.0.1:3901`. The service requires the SSD and starts at boot.
Ansible generates credentials once in `s3-bootstrap.env` (`0600 root:root`).

`playbooks/local-plan.yml` manages the `cavespace-local-plan` key with read-only
access to `terraform-state`. Its private AWS profile is stored at
`/srv/terraform/workspaces/garage-readonly.credentials` (`0600 capcom:capcom`).
See [local Terraform plans](../../terraform/LOCAL_PLAN.md).

```bash
systemctl is-active garage.service
sudo -u garage-svc garage status
sudo -u garage-svc garage bucket info terraform-state
```

Garage has one local data copy. [Terraform operations](../../terraform/README.md)
and [verified R2 snapshots](../../terraform/R2_BACKUP.md) cover state access
and recovery.

## Terraform and locking

`/usr/local/bin/terraform` requires the SSD and holds `flock` on
`/run/houston-terraform/operation.lock` for each command. `capcom` and
`runner-svc` share access through `terraform-ops`. Ansible preserves the
lock inode; systemd-tmpfiles recreates it at boot.

Garage lacks the conditional writes required for native S3 locking, so
`use_lockfile = false`. Use the wrapper for all manual and runner commands;
the versioned binary bypasses this lock. Local plans hold it through SSH.
It covers individual commands, not complete workflows. Inspect `lslocks` and
processes if a command waits; never delete the lock file.

Update Terraform's Ansible version/checksums and `aqua.yaml` pin together.
Garage, Terraform and runner downloads are checksum-verified.

## Workspaces and backup staging

| Path under `/srv/terraform` | Access and purpose |
| --- | --- |
| `workspaces` | Operator checkouts; `0700 capcom:capcom`. |
| `runner/{home,work,tmp,app-<version>}` | Private runner directories on SSD. |
| `backup-staging` | `1770 root:terraform-ops`; private per-operation subdirectories. |
| `tools` | Root-owned executables and release archives. |

Successful backups remove staging. Failed operations and restore diagnostics
retain private files; preserve recovery material before cleanup.

## Runner registration and service

The runner registers only to private
[`bart-kochanowicz/homelab-automation`](https://github.com/bart-kochanowicz/homelab-automation).
It runs as `runner-svc` without sudo, with labels `houston,terraform`, automatic
updates disabled and identity files at mode `0600`. The systemd service uses
packaged `runsvc.sh` and requires the SSD. Public CI runs on GitHub-hosted runners.

A new registration needs the short-lived Linux/x64 token from the private
repository's **Settings → Actions → Runners → New self-hosted runner**:

```bash
set +x
printf 'GitHub runner registration token: '
read -r -s GITHUB_RUNNER_REGISTRATION_TOKEN
printf '\n'
export GITHUB_RUNNER_REGISTRATION_TOKEN
ansible-playbook playbooks/houston.yml --tags github_runner --ask-become-pass
unset GITHUB_RUNNER_REGISTRATION_TOKEN
```

Repeat applies validate registration and need no token. Unexpected or
incomplete registration requires inspection. Verify
`systemctl is-active github-runner.service` and runner `houston-01` online in
GitHub. Stop and unregister an idle runner before changing its versioned
installation, then apply the new pin with a fresh token. Keep the pinned runner
current with [GitHub's update requirements](https://docs.github.com/en/actions/reference/runners/self-hosted-runners#runner-software-updates-on-self-hosted-runners).

## Recovery

Correct failed downloads and reapply the affected role. Rebuild a lost host
through Ansible, then restore matching Terraform state from verified backups;
update private Actions secrets if Garage keys change.

Before removing the host, preserve Garage data and snapshots, stop jobs and
unregister the runner using its removal token. Deleting runner identity files
does not unregister it. Deleting `/srv/terraform/garage` removes the local
objects, metadata and RPC secret.

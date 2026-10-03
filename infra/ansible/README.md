# Houston configuration and operations

`houston-01` is a Debian 13 Dell Wyse 3040 dedicated to Terraform operations.
Debian boots from eMMC; mutable workloads live on the external ext4 SSD
mounted at `/srv/terraform`, with filesystem label `houston-data`.

## Managed components

| Role | Configuration |
| --- | --- |
| `common` | Timezone, NTP, unattended security updates, and bounded journald storage. |
| `storage` | Persistent mount by the verified SSD UUID and scheduled TRIM. |
| `garage` | Native Garage 2.4.1, its single-node layout, `terraform-state` bucket, and bootstrap S3 key. |
| `terraform_cli` | Terraform 1.16.4, the shared host lock, private operator workspace, and backup staging tools. |
| `github_runner` | Native runner 2.337.0, registration to the private automation repository, and systemd service. |

No role formats disks, changes SSH configuration, or reboots the host.
Garage runs as `garage-svc`; Actions jobs run as `runner-svc` without sudo.
The runner belongs to `terraform-ops` solely to use the shared Terraform lock.

## Controller setup

Run Ansible from your computer. The `houston-01` SSH alias supplies the host
address and SSH key outside Git; the inventory selects the remote `capcom`
account. `system/bootstrap.yaml` is a separate local Kubernetes bootstrap
playbook and uses the same controller-side Ansible installation.

```bash
cd infra/ansible
ansible-galaxy collection install -r requirements.yml
ansible-inventory --graph
ansible houston-01 -m ping
ansible-playbook playbooks/houston.yml --syntax-check
```

`pong` verifies SSH and remote Ansible module execution. `--ask-become-pass`
in the commands below asks for `capcom`'s remote sudo password; it is separate
from SSH authentication and GitHub tokens.

## Apply and verify configuration

The playbook always checks the SSD label, ext4 filesystem, partition UUID,
and mounted UUID before applying roles. To run only this read-only preflight:

```bash
ansible-playbook playbooks/houston.yml --tags always --ask-become-pass
```

For an already registered host, review and apply the complete desired state:

```bash
ansible-playbook playbooks/houston.yml --check --diff --ask-become-pass
ansible-playbook playbooks/houston.yml --ask-become-pass
ansible-playbook playbooks/houston.yml --ask-become-pass
```

The second normal apply should report `changed=0`. Restrict an operation with
`--tags common`, `storage`, `garage`, `terraform_cli`, or `github_runner` when
needed; SSD preflight still runs. Initial runner registration needs the token
procedure below before the first full apply. Fresh-host check mode skips
operations that require downloaded binaries or generated secrets.

Open a new SSH session after changes to account group membership. Apply
runner service changes while the runner is idle because its handler restarts
the service.

## Garage

The root-owned binary is linked at `/usr/local/bin/garage`. `/etc/garage.toml`
configures the service; its RPC secret, metadata, and objects live under
`/srv/terraform/garage`. S3 listens on `127.0.0.1:3900`; RPC listens on
`127.0.0.1:3901`. The service requires the SSD mount and starts at boot.

Ansible generates the bootstrap access key once and stores it in
`/srv/terraform/garage/s3-bootstrap.env`, owned by `root:root` with mode `0600`.
The service receives it through systemd and creates the default bucket and
key during single-node bootstrap. Keep the file private; copy values only
into a password manager or the private repository's Actions secrets.

Verify on Houston:

```bash
systemctl is-enabled garage.service
systemctl is-active garage.service
sudo -u garage-svc garage status
sudo -u garage-svc garage bucket info terraform-state
sudo stat -c '%a %U:%G %n' /srv/terraform/garage/s3-bootstrap.env
```

Expect a healthy single node, the `terraform-state` bucket, and
`600 root:root` for the credential file. Garage has one local data copy;
verified R2 snapshots provide off-site recovery material. See
[backend operations](../../terraform/BACKEND.md) and
[R2 backup operations](../../terraform/R2_BACKUP.md).

## Terraform and locking

All Terraform operations on Houston use `/usr/local/bin/terraform`. This
root-owned wrapper requires the SSD mount and acquires Linux `flock` on
`/run/houston-terraform/operation.lock` before running the pinned executable.
Manual commands and runner jobs use the same lock; a second command waits.
The lock covers one Terraform command, not an entire workflow.

The lock file is `660 root:terraform-ops` in a root-owned directory. Ansible
preserves its inode and systemd-tmpfiles recreates it at boot. `capcom` and
`runner-svc` belong to `terraform-ops`. Never remove the lock file to unblock
a command; inspect `lslocks` and the running process instead.

Garage 2.4.1 lacks the conditional writes needed by native S3 state locking.
`terraform/garage.s3.tfbackend` therefore sets `use_lockfile = false`.
Do not bypass the wrapper with the versioned binary or run Terraform against
Garage from another host. The shared lock is an operational rule for trusted
users, not a security sandbox.

```bash
terraform version
command -v terraform
id capcom
id runner-svc
sudo stat -c '%F %a %U:%G %n' \
  /usr/local/bin/terraform /run/houston-terraform/operation.lock
```

Expect Terraform 1.16.4 and a regular wrapper at `/usr/local/bin/terraform`.
Upgrade the Ansible version/checksums and `aqua.yaml` pin together. Garage and
Terraform downloads are checksum-verified before installation.

## Workspaces and backup staging

| Path | Purpose and access |
| --- | --- |
| `/srv/terraform/workspaces` | Private operator checkouts; `700 capcom:capcom`. |
| `/srv/terraform/runner/work` | Actions workspaces; private to `runner-svc`. |
| `/srv/terraform/runner/tmp` | SSD-backed runner temporary storage. |
| `/srv/terraform/backup-staging` | `1770 root:terraform-ops`; scripts create private `0700` subdirectories and `0600` files. |
| `/srv/terraform/tools` | Root-owned versioned Terraform executable and verified release archives. |

The sticky bit on backup staging prevents the two accounts from removing each
other's directories. Successful backup scripts remove temporary copies;
failed operations and restore rehearsals retain private files for inspection.
Preserve recovery material before deliberate cleanup. Do not treat Garage
objects, credentials, runner identity, or protected R2 snapshots as temporary
files.

The `terraform_cli` role supplies curl, CA certificates, and Python 3 for
backup scripts. Production jobs also remove their private plan and Terraform
working metadata on shell exit.

## Runner registration and service

Register Houston only to
[`bart-kochanowicz/homelab-automation`](https://github.com/bart-kochanowicz/homelab-automation).
Keep that repository private with trusted write access. Public pull request
validation and dispatch run on GitHub-hosted machines; the private workflow
verifies reviewed `homelab/main` commits before assigning production jobs.

For initial registration, obtain the short-lived token from the private
repository's **Settings → Actions → Runners → New self-hosted runner**,
selecting Linux/x64. Ansible handles downloading, registration, and service
setup; supply only that token on your controller:

```bash
set +x
printf 'GitHub runner registration token: '
read -r -s GITHUB_RUNNER_REGISTRATION_TOKEN
printf '\n'
export GITHUB_RUNNER_REGISTRATION_TOKEN
ansible-playbook playbooks/houston.yml --tags github_runner --ask-become-pass
unset GITHUB_RUNNER_REGISTRATION_TOKEN
ansible-playbook playbooks/houston.yml --tags github_runner --ask-become-pass
```

Repeat applies need no registration token and should report `changed=0`.
The role validates existing registration settings instead of replacing them.
An incomplete or unexpected registration needs inspection before retrying.

The service uses packaged `runsvc.sh`, starts at boot, requires the SSD,
and uses a private umask. Runner home, work, application, and temporary
directories are private to `runner-svc`; registration identity files are
`0600`. It has LAN access, so private repository access remains a trust boundary.

```bash
systemctl is-enabled github-runner.service
systemctl is-active github-runner.service
sudo stat -c '%a %U:%G %n' \
  /srv/terraform/runner/app-2.337.0/{.runner,.credentials,.credentials_rsaparams}
```

Expect `enabled`, `active`, and `600 runner-svc:runner-svc` identity files.
GitHub should show runner `houston-01` online with labels `self-hosted`,
`Linux`, `X64`, `houston`, and `terraform`. Follow the
[private automation guide](https://github.com/bart-kochanowicz/homelab-automation)
for production dispatch, secrets, backups, and diagnostic workflows.

Automatic runner updates are disabled. Keep the pin current: GitHub requires
updates within 30 days of a new release and can block jobs sooner for critical
security updates. Stop and unregister an idle runner before changing its
versioned installation, then apply the new pin with a new registration token.

## Recovery and decommissioning

For failed downloads or incomplete installation, correct the cause and
reapply the relevant role. Recover a failed or missing host through Ansible,
then deliberately restore the matching Terraform state from verified backups.
Update private Actions secrets if Garage keys change.

Before decommissioning, preserve Garage data and required snapshots. Remove
roles from the desired playbook before removing their managed services.
Stop and unregister the runner in GitHub using its short-lived removal token,
then remove its service and files. Do not delete identity files as a substitute
for unregistering. Remove Terraform locking only after choosing a replacement
and stopping all jobs. Deleting `/srv/terraform/garage` permanently removes
its local objects, metadata, and RPC secret.

References: [Garage bootstrap](https://garagehq.deuxfleurs.fr/documentation/quick-start/),
[Terraform S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3),
[runner registration](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners),
[runner update requirements](https://docs.github.com/en/actions/reference/runners/self-hosted-runners#runner-software-updates-on-self-hosted-runners).

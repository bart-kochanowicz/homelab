# houston-01: step 1 — connection

`houston-01` is a Dell Wyse 3040 that will eventually manage Terraform state.
This first step only tells Ansible which machine to contact. It installs
nothing and does not change the server configuration.

The repository already uses Ansible in `system/bootstrap.yaml` to bootstrap
ArgoCD from the local machine. This inventory serves a different target: the
remote Debian host `houston-01`. Both use the same Ansible installation.

## What do these files do?

- `ansible.cfg` tells Ansible where to find the host inventory.
- `inventory/hosts.yml` places `houston-01` in the `terraform_hosts` group.
  `ansible_host` refers to the existing SSH alias, while `ansible_user` names
  the `capcom` account on the server.
- The IP address and SSH key remain in the local SSH configuration outside
  this repository. An address change therefore does not require an inventory
  edit.

## How can I check the connection?

On your computer, with Ansible installed and the SSH alias working:

```bash
cd infra/ansible
ansible-inventory --graph
ansible houston-01 -m ping
```

The first command should show `houston-01` in `terraform_hosts`. The second
uses SSH to run an Ansible module; `pong` means Ansible can run a simple
module on the server. It does not require `sudo` and is not an ICMP network
ping.

## Step 2 — verify the SSD

Before Ansible configures the host, it checks that `/dev/sda1` has the
expected `houston-data` label, uses ext4, and is mounted at
`/srv/terraform`. It compares the partition UUID with the mounted filesystem
UUID, so an unrelated disk mounted at that path does not pass the check.

The playbook in `playbooks/houston.yml` contains only read-only checks. It
does not format or mount disks, install packages, or modify configuration.
`become` is used so the filesystem identity can be read reliably.

Check the syntax locally, then run the read-only checks against the host:

```bash
ansible-playbook playbooks/houston.yml --syntax-check
ansible-playbook playbooks/houston.yml --ask-become-pass
```

The second command asks for the sudo password locally. A successful run
confirms the storage is ready for later configuration steps.

## Step 3 — apply the Debian baseline

The `common` role manages the timezone, NTP, unattended security updates, and
journald limits. It does not change SSH settings or reboot the host. Journald
restarts only if its configuration file changes.

Install the Ansible collection and review the proposed changes before
applying them:

```bash
ansible-galaxy collection install -r requirements.yml
ansible-playbook playbooks/houston.yml --syntax-check
ansible-playbook playbooks/houston.yml --check --diff --tags common --ask-become-pass
ansible-playbook playbooks/houston.yml --tags common --ask-become-pass
ansible-playbook playbooks/houston.yml --tags common --ask-become-pass
```

The final run checks idempotency: if the host already matches the desired
settings, Ansible should report no changes.

## Step 4 — keep the SSD mount across reboots

The `storage` role records the already-verified filesystem UUID in
`/etc/fstab` and enables the systemd `fstrim.timer`. The mount task uses
`state: present`, which manages the boot-time entry without mounting or
formatting the disk. The earlier preflight must pass before this role runs.

Review the proposed `/etc/fstab` and timer changes, then apply the role and
run it again to check idempotency:

```bash
ansible-galaxy collection install -r requirements.yml
ansible-playbook playbooks/houston.yml --syntax-check
ansible-playbook playbooks/houston.yml --check --diff --tags storage --ask-become-pass
ansible-playbook playbooks/houston.yml --tags storage --ask-become-pass
ansible-playbook playbooks/houston.yml --tags storage --ask-become-pass
```

## Step 5 — install Garage

The `garage` role installs the pinned Garage binary and links it to the stable
command `/usr/local/bin/garage`. The service runs as the dedicated `garage-svc`
user, while `garage` is the CLI command. Its metadata and objects live on the
SSD under `/srv/terraform/garage`. Its S3 API and internal RPC listener bind to
localhost, so other machines cannot connect to them. The service also requires
the SSD mountpoint and will not start against the small eMMC root filesystem.

This step installs the service only. It does not create an S3 bucket, access
key, or Terraform backend. Garage is configured as a single node with one copy
of its data, so off-site backups will be needed before it stores important
state.

Review the proposed changes, apply them, and run the role again to check
idempotency:

```bash
ansible-galaxy collection install -r requirements.yml
ansible-playbook playbooks/houston.yml --syntax-check
ansible-playbook playbooks/houston.yml --check --diff --tags garage --ask-become-pass
ansible-playbook playbooks/houston.yml --tags garage --ask-become-pass
ansible-playbook playbooks/houston.yml --tags garage --ask-become-pass
```

The first apply downloads the binary from the [official Garage release
site](https://garagehq.deuxfleurs.fr/_releases.html) and verifies its SHA-256
checksum. It creates a private RPC secret on the SSD; Ansible suppresses that
task's output so the value is not printed. Check mode skips secret generation
because it must not create the secret as a side effect.

Verify the service and its local listeners on `houston-01`:

```bash
sudo systemctl status garage --no-pager
sudo ss -ltnp | grep -E '127\.0\.0\.1:(3900|3901)'
```

To stop the service while keeping its data, run
`sudo systemctl disable --now garage`. Its config is `/etc/garage.toml`; the
binary, secret, metadata, and objects are under `/srv/terraform/garage`.
Preserve that directory before removing it, because deleting it permanently
removes the local Garage data and RPC secret.

## Step 6 — bootstrap the Terraform bucket and access key

Garage's `--single-node` flag initializes its one-node layout. The
`--default-bucket` flag creates the `terraform-state` bucket and an S3 access
key on startup. Ansible generates the key ID and secret once, stores them in a
root-only environment file on the SSD, and tells systemd to pass them to
Garage. The secret is not printed by Ansible or committed to Git. This follows
Garage's [official single-node bootstrap
flow](https://garagehq.deuxfleurs.fr/documentation/quick-start/).

Review and apply the bootstrap, then run it again to check idempotency:

```bash
ansible-galaxy collection install -r requirements.yml
ansible-playbook playbooks/houston.yml --syntax-check
ansible-playbook playbooks/houston.yml --check --diff --tags garage --ask-become-pass
ansible-playbook playbooks/houston.yml --tags garage --ask-become-pass
ansible-playbook playbooks/houston.yml --tags garage --ask-become-pass
```

The first apply creates `/srv/terraform/garage/s3-bootstrap.env` with mode
`0600`, links the pinned binary to `/usr/local/bin/garage`, and restarts Garage
so it can create the bucket and access key. The credentials file is root-only;
do not paste its contents into chat or commit it. When you need to copy the
credentials to a password manager or a future runner secret store, read the
file with `sudo` and handle the output as a secret.

Verify Garage is healthy and that the bucket and access key exist:

```bash
sudo -u garage-svc garage status
sudo -u garage-svc garage bucket info terraform-state
sudo -u garage-svc garage key list
sudo stat -c '%a %U:%G %n' /srv/terraform/garage/s3-bootstrap.env
```

The permissions check should show `600 root:root`. Terraform is not configured
to use this bucket in this step; backend setup and state-locking verification
come later.

## Step 7 — install Terraform CLI

The `terraform_cli` role installs Terraform 1.16.4 from the [official HashiCorp
release](https://releases.hashicorp.com/terraform/1.16.4/). This is the command
that the future infrastructure runner will use for `plan` and `apply`.
The laptop/CI pin in `aqua.yaml` uses the same version. Change that pin and
`terraform_cli_version` together when upgrading, and update both checksums.

Ansible verifies the downloaded ZIP against HashiCorp's [published
SHA-256](https://releases.hashicorp.com/terraform/1.16.4/terraform_1.16.4_SHA256SUMS).
The executable checksum is derived from that verified ZIP. Downloads and the
versioned executable live under `/srv/terraform/tools` on the SSD.
`/usr/local/bin/terraform` is a root-owned wrapper that runs the executable
with the shared Houston process lock described in step 9. The executable and
wrapper belong to `root:root`.
The role checks the executable checksum first and reinstalls it only when it
is missing or differs from the pinned release.

From `infra/ansible` on your computer, review the changes, apply them, and
repeat the apply to verify idempotency:

```bash
ansible-playbook playbooks/houston.yml --syntax-check
ansible-playbook playbooks/houston.yml --check --diff --tags terraform_cli --ask-become-pass
ansible-playbook playbooks/houston.yml --tags terraform_cli --ask-become-pass
ansible-playbook playbooks/houston.yml --tags terraform_cli --ask-become-pass
```

On a fresh host, check mode reports the planned installation but skips
archive extraction because it has not downloaded the archive. An unchanged
installation should report `changed=0` in both check mode and a normal apply.

Verify on `houston-01` as `capcom`, without sudo:

```bash
terraform version
command -v terraform
stat -c '%F %U:%G %n' /usr/local/bin/terraform
```

Expect version `1.16.4`, command path `/usr/local/bin/terraform`, and a regular
file owned by `root:root`. This step installs the CLI;
backend configuration, runner registration, and state locking are later steps.

To roll back an upgrade, restore the previous version and its two checksums
from Git, restore the matching `aqua.yaml` pin, then apply the role again.
To remove the CLI, remove the role from the playbook and unlink
`/usr/local/bin/terraform` with `sudo rm /usr/local/bin/terraform`.
The versioned installation and ZIP remain on the SSD for explicit cleanup.

## Step 8 — install the GitHub Actions runner

The `github_runner` role installs the official Linux x64 runner **2.337.0** and
its Debian 13 runtime libraries. It creates `runner-svc`, a separate system
account with a locked password, no login shell, and only the `terraform-ops`
supplementary group needed for the shared process lock.
The runner application, home, future job workspace, and temporary directory
live under `/srv/terraform/runner` on the SSD. These directories are private
to the runner account. The application belongs to `runner-svc`, following the
runner's normal installation model; it does not grant the account sudo access.

The archive checksum comes from the [official release](https://github.com/actions/runner/releases/tag/v2.337.0).
The executable checksum was calculated from that verified archive. Ansible
checks the executable before downloading or extracting it, then checks its
reported version. The runner bundles its own .NET and Node runtimes; a separate
Node installation is not needed.

Installation is followed by the registration and service setup in
[Step 11](#step-11--register-the-private-infrastructure-runner). Initial
registration requires a short-lived GitHub token; repeat applies do not.
This repository is public: GitHub [recommends private repositories for
self-hosted runners](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners).
Before registration, define which trusted jobs may use Houston. Pull request
validation must continue to run on GitHub-hosted runners.

Installation and registration share the `github_runner` tag. Use the complete
controller commands in Step 11, including the initial registration token.

On a fresh host, check mode reports the proposed installation and skips
extraction, registration, and execution because the archive has not been
downloaded. Follow Step 11 before the first normal apply. The second normal
apply should report `changed=0`.

Verify on `houston-01`:

```bash
getent passwd runner-svc
id runner-svc
sudo -u runner-svc /srv/terraform/runner/app-2.337.0/bin/Runner.Listener --version
sudo stat -c '%a %U:%G %n' /srv/terraform/runner/{home,work,tmp,app-2.337.0}
```

Expect version `2.337.0` and `700 runner-svc:runner-svc` for the four private
directories. Registration and the service are verified in Step 11.

To retry an incomplete installation, apply the role again. To remove this
unregistered installation, first remove the role from the playbook. Preserve
any needed files, then explicitly remove `/srv/terraform/runner` and its
release archive under `/srv/terraform/tools/archives`, followed by the unused
`runner-svc` account and group. Do not use this removal procedure once a runner
has been registered; unregister and stop its service first.

## Step 9 — serialize Terraform commands on Houston

Garage 2.4.1 cannot provide the conditional writes required by Terraform's
native S3 locking. We keep Garage and use one host-wide Linux `flock` instead.
All normal Terraform invocations on Houston must use `/usr/local/bin/terraform`,
including manual commands and future runner jobs. This wrapper acquires
`/run/houston-terraform/operation.lock` before executing the pinned binary.
A second invocation waits until the first finishes. The same lock covers all
commands and state keys, which is deliberately simple for this small host.

The `terraform-ops` group gives `capcom` and `runner-svc` access to the lock.
Its root-owned parent directory prevents either account from replacing or
removing the lock file. Ansible preserves the lock file's inode when enforcing
permissions; replacing a file that is already locked could allow two separate
locks to exist. `systemd-tmpfiles` recreates the directory and file at boot.
The kernel releases the lock after all processes holding its file descriptor
have closed it or exited.
The wrapper also refuses to run if the SSD mountpoint is unavailable.

This is an operational rule for trusted users and workflows, not a security
sandbox. Do not invoke the versioned binary directly, run Terraform from
another machine against this bucket, or delete the runtime lock while a
command is running. Those actions bypass the shared lock. A future Garage
S3 backend must set `use_lockfile = false` because locking is external.
The backend is not changed by this step.

Apply both tags so the runner account receives its lock group:

```bash
ansible-playbook playbooks/houston.yml --syntax-check
ansible-playbook playbooks/houston.yml --check --diff --tags terraform_cli,github_runner --ask-become-pass
ansible-playbook playbooks/houston.yml --tags terraform_cli,github_runner --ask-become-pass
ansible-playbook playbooks/houston.yml --tags terraform_cli,github_runner --ask-become-pass
```

Open a new SSH session as `capcom` after group membership changes. Verify:

```bash
id capcom
id runner-svc
terraform version
sudo stat -c '%F %a %U:%G %n' /usr/local/bin/terraform /run/houston-terraform/operation.lock
```

Expect both accounts in `terraform-ops`, a root-owned regular wrapper, and a
`660 root:terraform-ops` lock file. To check waiting, hold the same lock in one
terminal with `flock /run/houston-terraform/operation.lock sleep 15`, then run
`terraform version` in another. It should print the version after the lock
holder exits. The final Ansible apply should report `changed=0`.

If a command waits unexpectedly, inspect running Terraform processes and
`lslocks`; stop the responsible command deliberately. Do not remove the lock
file to unblock a waiter. To remove this design, first stop all Terraform jobs
and decide on a replacement locking mechanism, then remove the wrapper and
its Ansible tasks, tmpfiles configuration, runtime directory, and unused group.
Never revert to concurrent unlocked access to important state.

## Step 10 — prepare state backup staging

The `terraform_cli` role installs `curl`, CA certificates, and Python 3 for
`backup-terraform-state.sh`. It creates `/srv/terraform/backup-staging` as
`root:terraform-ops` with mode `1770`. The group lets `capcom` and `runner-svc`
create staging directories. The sticky bit prevents either account from
removing the other's directories. Each script run creates its own private
`0700` directory and `0600` files on the SSD.

From `infra/ansible` on your computer:

```bash
ansible-playbook playbooks/houston.yml --syntax-check
ansible-playbook playbooks/houston.yml --check --diff --tags terraform_cli --ask-become-pass
ansible-playbook playbooks/houston.yml --tags terraform_cli --ask-become-pass
ansible-playbook playbooks/houston.yml --tags terraform_cli --ask-become-pass
```

Expect `changed=0` on the second normal apply. On Houston, verify:

```bash
sudo stat -c '%a %U:%G %n' /srv/terraform/backup-staging
curl --version
python3 --version
```

Expect `1770 root:terraform-ops` for staging. See the
[R2 guide](../../terraform/R2_BACKUP.md#upload-and-read-back-an-isolated-snapshot)
for the first upload. Successful runs remove their temporary files; failures
retain private staging for recovery. After preserving any needed snapshots,
remove their directories explicitly. To remove staging permanently, first
remove its Ansible task so later applies do not recreate it.

## Step 11 — register the private infrastructure runner

Houston is registered only to the private repository
[`bart-kochanowicz/homelab-automation`](https://github.com/bart-kochanowicz/homelab-automation).
This repository contains trusted workflows. Infrastructure code stays in the
public `homelab` repository; its PR validation runs on GitHub-hosted machines.
Future Houston workflows must execute reviewed infrastructure revisions.
Keep access to the private repository limited to trusted operators and keep
its visibility private.

The `github_runner` role registers `houston-01` with the default
`self-hosted`, `Linux`, `X64` labels plus `houston` and `terraform`.
Its work directory is `/srv/terraform/runner/work`. It checks an existing
registration against the intended repository, name, work directory and
update policy before starting the service. It does not replace an existing
registration automatically. A local registration does not prove that its
identity still exists in GitHub; verify the runner is online in the dashboard.

Supply a short-lived registration token on the Ansible controller through
`GITHUB_RUNNER_REGISTRATION_TOKEN`. The role passes it through the runner's
supported `ACTIONS_RUNNER_INPUT_TOKEN` environment variable, with Ansible
output hidden by `no_log`. The token is not passed in runner configuration arguments or saved in
inventory. The runner persists its own private identity files on the
SSD; these are restricted to `runner-svc` with mode `0600`.

In the private repository, open **Settings → Actions → Runners → New
self-hosted runner**, select **Linux / x64**, and copy only the temporary
registration token from the displayed configuration command. Do not execute
its download or service commands: Ansible manages the installed application
and service. The registration token expires after one hour.

From `infra/ansible` on your computer, in Bash or Zsh:

```bash
ansible-playbook playbooks/houston.yml --syntax-check
ansible-playbook playbooks/houston.yml --check --diff --tags github_runner --ask-become-pass

set +x
printf 'GitHub runner registration token: '
read -r -s GITHUB_RUNNER_REGISTRATION_TOKEN; printf '\n'
export GITHUB_RUNNER_REGISTRATION_TOKEN
ansible-playbook playbooks/houston.yml --tags github_runner --ask-become-pass
unset GITHUB_RUNNER_REGISTRATION_TOKEN

ansible-playbook playbooks/houston.yml --tags github_runner --ask-become-pass
```

A fresh check-mode run skips registration and service activation. The normal
apply registers and starts the runner; the second apply needs no token and
should report `changed=0`. If registration fails before creating `.runner`,
obtain a new token and retry. If settings or identity files are incomplete or
unexpected, stop and inspect the registration instead of overwriting them.

Ansible copies the packaged `bin/runsvc.sh` to the application root with mode
`0755`, matching the official service installer. It owns
`github-runner.service`, which uses this entry point as `runner-svc`. It starts
at boot and requires the SSD mount.
Home, temporary files, and workspaces use the SSD. The service uses a private
umask, grants no sudo access, and restricts filesystem writes to runner data,
backup staging, and the existing Terraform lock directory. It still has LAN
access; the private repository is a trust boundary, not a sandbox for hostile
jobs. Apply service changes while the runner is idle: its handler restarts it.

Verify on Houston:

```bash
systemctl is-enabled github-runner.service
systemctl is-active github-runner.service
sudo systemctl status github-runner.service --no-pager -l
sudo stat -c '%a %U:%G %n' /srv/terraform/runner/app-2.337.0/{.runner,.credentials,.credentials_rsaparams}
```

Expect `enabled`, `active`, and `600 runner-svc:runner-svc` identity files.
The private repository's runner page should show `houston-01` online and idle.
No workflow or Terraform apply is triggered by registration alone.

Automatic runner updates are disabled to preserve the version and checksums
managed by Ansible. Keep the pin current: GitHub requires an update within
30 days of a new release and may block jobs sooner for critical security
updates. Stop and unregister an idle runner before changing the versioned
installation, then apply the updated pin with a new registration token.

To remove the runner, first remove its role from the desired playbook so the
next apply will not recreate it. While idle, stop and disable
`github-runner.service`. In the private repository's runner page choose
**Remove** and use its short-lived removal token with the installed
`config.sh remove`, run as `runner-svc`; keep the token out of shell history
and arguments by supplying `ACTIONS_RUNNER_INPUT_TOKEN`. After unregistering,
remove the unit and reload systemd. Preserve any needed SSD files before
explicitly removing the installation and the unused account. Do not delete
its private identity files as a substitute for unregistering it in GitHub.

References: [runner registration](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners),
[custom systemd services](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/configure-the-application?platform=linux),
[runner update requirements](https://docs.github.com/en/actions/reference/runners/self-hosted-runners#runner-software-updates-on-self-hosted-runners).

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

The `garage` role installs the pinned Garage binary and runs it as a dedicated
system user. Garage metadata and objects live on the SSD under
`/srv/terraform/garage`. Its S3 API and internal RPC listener bind to localhost,
so other machines cannot connect to them. The service also requires the SSD
mountpoint and will not start against the small eMMC root filesystem.

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

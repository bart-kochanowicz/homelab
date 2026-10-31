# Houston

`houston-01` is a Dell Wyse 3040 running Debian 13. Debian boots from eMMC;
Garage, Terraform workspaces and the private Actions runner use the ext4 SSD
labelled `houston-data`, mounted at `/srv/terraform`.

| Role | Configuration |
| --- | --- |
| `common` | Warsaw timezone, NTP, security updates and journald limits |
| `alloy` | Journal forwarding to Loki; collector state on the SSD |
| `storage` | SSD mount, scheduled TRIM and private Talos recovery directory |
| `garage` | Garage 2.4.1, `terraform-state` bucket and S3 credentials |
| `terraform_cli` | Terraform 1.16.4, shared lock and backup tools |
| `restic_server` | Private TLS endpoint for encrypted application backup repositories |
| `github_runner` | Private runner 2.337.0 and its systemd service |

## Configure the host

The controller uses its `houston-01` SSH alias and the inventory's `capcom` user.
The playbook checks the disk label, filesystem and mounted UUID before each role;
it does not format disks.

```bash
cd infra/ansible
ansible-galaxy collection install -r requirements.yml
ansible-playbook playbooks/houston.yml --syntax-check
ansible-playbook playbooks/houston.yml --check --diff --ask-become-pass
ansible-playbook playbooks/houston.yml --ask-become-pass
```

Tags match the role names; `--tags always` runs only the disk checks. On a fresh
host, check mode skips tasks that need downloaded binaries or generated secrets.
Open a new SSH session after group changes. Apply runner service changes while
no job is running. Downloads for Garage, Terraform and the runner use pinned checksums.

## Garage and files

Garage runs as `garage-svc`, using `/etc/garage.toml` and
`/srv/terraform/garage`. S3 listens on `127.0.0.1:3900`; RPC uses
`127.0.0.1:3901`. The service requires the SSD and starts at boot.
Credentials are generated once in `s3-bootstrap.env`, mode `600`, owned by root.

`playbooks/local-plan.yml` creates the read-only `cavespace-local-plan` S3 key.
Its profile is stored in `/srv/terraform/workspaces/garage-readonly.credentials`,
mode `600`, owned by `capcom`. See [local plans](../../terraform/LOCAL_PLAN.md).

| Path under `/srv/terraform` | Purpose / permissions |
| --- | --- |
| `garage` | Garage objects, metadata and service credentials |
| `workspaces` | Operator checkouts, `700 capcom:capcom` |
| `runner/{home,work,tmp,app-<version>}` | Private runner files |
| `backups/talos` | Encrypted Talos recovery repository over SFTP, `700 capcom:capcom` |
| `backups/restic` | Encrypted application repositories, `700 restic-svc:restic-svc` |
| `backup-staging` | Per-operation directories, `1770 root:terraform-ops` |
| `tools` | Root-owned executables and release archives |

Garage has one local data copy. [R2 backups](../../terraform/R2_BACKUP.md) provide
state recovery. Successful backups remove staging; failures retain private files
for diagnosis and recovery.

```bash
systemctl is-active garage.service
sudo -u garage-svc garage status
sudo -u garage-svc garage bucket info terraform-state
```

## Terraform and locking

`/usr/local/bin/terraform` requires the SSD and holds `flock` on
`/run/houston-terraform/operation.lock` for each command. `capcom` and
`runner-svc` share access through `terraform-ops`. Ansible preserves the lock
inode; systemd-tmpfiles creates it at boot.

Garage does not support native S3 locking, so backend `use_lockfile` is false.
Use `/usr/local/bin/terraform` for host commands; the versioned binary bypasses
the shared lock. Local plans hold it through SSH. The wrapper locks individual
commands, not an entire workflow. Inspect `lslocks` and processes if a command
waits; deleting the lock file breaks coordination.

Update the Ansible Terraform version/checksums and `aqua.yaml` pin together.

## Actions runner

The runner belongs to private
[`bart-kochanowicz/homelab-automation`](https://github.com/bart-kochanowicz/homelab-automation).
It runs as `runner-svc` without sudo, with labels `houston,terraform`. Automatic
runner updates are disabled. Public CI uses GitHub-hosted runners.
`github-runner.service` uses packaged `runsvc.sh` and requires the SSD;
registration identity files have mode `600`.

New registrations need a short-lived Linux/x64 token from the private repository's
**Settings → Actions → Runners → New self-hosted runner**:

```bash
set +x
printf 'GitHub runner registration token: '
read -r -s GITHUB_RUNNER_REGISTRATION_TOKEN
printf '\n'
export GITHUB_RUNNER_REGISTRATION_TOKEN
ansible-playbook playbooks/houston.yml --tags github_runner --ask-become-pass
unset GITHUB_RUNNER_REGISTRATION_TOKEN
```

Existing registrations need no token. Check `github-runner.service` and the
runner's online status in GitHub if registration is incomplete. For a version
change, stop and unregister the idle runner, then apply the new pin with a fresh
token. Follow [GitHub's runner update requirements](https://docs.github.com/en/actions/reference/runners/self-hosted-runners#runner-software-updates-on-self-hosted-runners).

## Application backup storage

The opt-in `restic_server` role installs checksum-pinned REST-server 0.14.0.
It listens on `10.0.70.10:8444` with TLS 1.3 and bcrypt authentication; systemd
allows connections only from the two cluster nodes and Houston itself. Private
repositories isolate the `home-assistant`, `n8n`, `monitoring` and `crafty-controller` users. A native
90 GiB limit covers **all repositories combined**, leaving SSD space for Garage.
K8up manages backup scheduling, retention and checks in Kubernetes; Houston needs
no Kubernetes credentials. Retention requires deletion, so append-only is disabled.

Supply absolute paths in an ignored mode-600 `.secrets/houston-restic.yml`:

```yaml
restic_server_enabled: true
restic_server_certificate_source: /absolute/private/path/server.crt
restic_server_private_key_source: /absolute/private/path/server.key
restic_server_htpasswd_source: /absolute/private/path/htpasswd
```

The key and htpasswd files must have mode `600`. The certificate must cover
`10.0.70.10` and `127.0.0.1` (SSH restores); distribute its trusted CA to the backup clients.
From the repository root:

```bash
ANSIBLE_CONFIG=infra/ansible/ansible.cfg ansible-playbook \
  infra/ansible/playbooks/houston.yml --tags restic_server --ask-become-pass \
  -e @.secrets/houston-restic.yml
ssh houston-01 'systemctl status restic-server.service'
```

Talos/etcd recovery copies use a separate encrypted repository over SSH/SFTP;
see [capture and recovery](../../docs/talos-etcd-recovery.md).

## Recovery

A lost host is rebuilt through Ansible, then matching Terraform state is restored
from R2. Update private Actions secrets if Garage keys change. Failed downloads
can be retried by applying the affected role.

Before decommissioning Houston, preserve Garage data and backups, stop jobs and
unregister the runner with its removal token. Removing identity files does not
unregister it. Removing `/srv/terraform/garage` deletes local objects, metadata
and the RPC secret.

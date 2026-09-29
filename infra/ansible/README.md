# houston-01: step 1 — connection

`houston-01` is a Dell Wyse 3040 that will eventually manage Terraform state.
This first step only tells Ansible which machine to contact. It installs
nothing and does not change the server configuration.

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

The next step will check the SSD before making any server changes.

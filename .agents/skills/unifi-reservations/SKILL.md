---
name: unifi-reservations
description: Add, change or remove a UniFi DHCP reservation (static IP) in terraform/unifi, with its private DNS name, firewall rules, MAC inputs, tests and the private Actions secret. Use when a device gets a fixed address, moves to another network or adapter, changes IP, or is retired.
---

# UniFi DHCP reservations

A reservation is a key in `local.dhcp_reservations`
(`terraform/unifi/reservations.tf`). Servers live in `local.server_reservations`
and are merged into it. Each key names a MAC in `var.infrastructure_macs`, and
other files refer to the device only through that key:

| Place | What refers to the key |
| --- | --- |
| `reservations.tf` | `mac`, `network`, `ip`, `allow_dynamic_pool` |
| `variables.tf` | exact key set and error message in the `infrastructure_macs` validation |
| `dns.tf` | `local.private_dns_records`, `address = local.dhcp_reservations["<key>"].ip` |
| `firewall.tf` | rule `source`/`destination` `zone` and `ips` |
| `terraform.tfvars.example` | placeholder MAC |
| `tests/authentication.tftest.hcl` | `override_resource`, three MAC maps, sensitivity assertion |
| `tests/firewall-baseline.tftest.hcl` | `override_resource`, MAC map, exact `private_dns_records` map, per-device runs, `least_privilege_access_matrix` |
| `README.md` | device paragraph under "Firewall and VPN" and the `infrastructure_macs` list |
| local `terraform.tfvars` (ignored) | real MAC |
| `UNIFI_INFRASTRUCTURE_MACS` in `bart-kochanowicz/homelab-automation` | real MAC, JSON object |

Start with `grep -rn '<key>\|<old-ip>' terraform/unifi --exclude-dir=.terraform`.
Repeat it at the end; only intended hits may remain.

## Address rules

- Networks (`networks.tf`): `endeavour` 30, `orbit` 40 (Home), `stardust` 50
  (IoT), `launchpad` 70 (Servers), `apollo` 80 (Admin), `mission-control` 90.
  Subnet `10.0.<vlan>.0/24`, gateway `.1`.
- DHCP pool is `.100`–`.199`. An address inside it needs
  `allow_dynamic_pool = true`; prefer the address the device already holds.
  The module rejects the gateway, other subnets, duplicate IPs and MACs.
- Use lowercase hyphenated keys. DNS names are `<name>.thecavespace.net`.
- Firewall rules reference `local.dhcp_reservations["<key>"].ip` and `.network`,
  never a literal address. Tests may assert the literal address.
- Ask the user for the MAC and current address. Never print real MACs in
  output, commits or docs; tests and examples use `02:00:00:00:00:xx`.

## Add

1. Add the reservation, the key in the `variables.tf` validation set and
   message, and a placeholder in `terraform.tfvars.example`.
2. Add DNS and firewall entries only when the device needs them. Keep rules
   least-privilege: specific source IPs, ports and `tcp`/`udp`.
3. Tests: add `override_resource` blocks and the key to every MAC map in both
   test files; extend the exact DNS map and `least_privilege_access_matrix` when
   DNS or cross-zone rules change; add a run asserting address and rules.
4. Document the device in `README.md`.
5. The `import` block in `reservations.tf` adopts the existing UniFi client;
   the plan shows an import, not a create.

## Change address, network or adapter

- Same MAC: edit `ip`/`network`; DNS and rules follow the key. Update literal
  addresses in tests and `README.md`.
- New adapter (new MAC): replace the MAC in the tfvars file and the secret, or add a
  new key and retire the old one with the steps below.
- Renew the device's DHCP lease after apply.

## Remove

1. Delete the reservation, its key in `variables.tf`, the example, the test
   overrides and MAC-map entries and `README.md` mentions. Repoint DNS and rules
   to the replacement key or delete them.
2. The plan destroys `module.reservations.unifi_client.this["<key>"]`. With
   `skip_forget_on_destroy` this only removes it from state; the provider makes
   no API call. Confirm the plan destroys no other reservation.
3. The client keeps its fixed IP in UniFi. Ask the user to clear it in the
   controller after apply.

## Private inputs

`infrastructure_macs` must contain exactly the validated keys, so the secret
matches only one side of the change: before merge it fits `main`, after merge
the branch. Update the secret and local `terraform.tfvars` right after merge
and before the next UniFi plan. GitHub cannot read secret values; rebuild the
secret from the user's local `terraform.tfvars` in the main checkout
(`~/Documents/development/homelab/terraform/unifi/terraform.tfvars`), never
echoing MACs:

```bash
python3 -I - "$TFVARS" <<'EOF' | gh secret set UNIFI_INFRASTRUCTURE_MACS -R bart-kochanowicz/homelab-automation
import json, re, sys
text = open(sys.argv[1]).read()
block = re.search(r'^infrastructure_macs\s*=\s*\{(.*?)^\}', text, re.S | re.M).group(1)
sys.stdout.write(json.dumps(dict(re.findall(r'^\s*([a-z0-9-]+)\s*=\s*"([^"]+)"', block, re.M))))
EOF
```

Edit the tfvars file first, assert the parsed key set equals the validation
set, and confirm with the user that the local file is current before
overwriting the secret.

## Check and deploy

1. `terraform fmt -recursive terraform`, then
   `terraform -chdir=terraform/unifi validate` and `terraform -chdir=terraform/unifi test`.
2. `make validate`.
3. Commit and open a PR only when the user asks.
4. After merge: update the secret and tfvars, then review a plan ([local plans](../../../terraform/LOCAL_PLAN.md) or the
   automation workflow) before any apply. The plan should show only the
   intended reservation, DNS and rule changes.

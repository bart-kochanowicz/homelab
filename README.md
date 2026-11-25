# Homelab

Home Assistant, n8n, Minecraft through Crafty Controller and an MQTT broker for the
front-door camera, running on a two-node Talos Kubernetes cluster. All application
endpoints are private.

ArgoCD deploys Kubernetes applications and platform services. Cilium handles
networking and firewall policies; Envoy Gateway and MetalLB provide private HTTPS
access. Prometheus, Grafana, Alertmanager, Loki and Alloy provide metrics, alerts
and logs. Terraform manages UniFi, Cloudflare and Crafty configuration; Ansible
manages Houston, the Terraform and backup host.

<p align="center">
  <img src="docs/images/homelab.jpg" width="520" alt="Homelab rack with two Lenovo ThinkCentre nodes and a Dell Wyse 3040.">
</p>

## Local checks

Install [Aqua](https://aquaproj.github.io/) for the pinned tools in
[`aqua.yaml`](aqua.yaml). Install yamllint, SQLite, Docker and Node.js 22.12+
separately; start Docker for the integration tests. Install the
[OpenSpec](https://github.com/Fission-AI/OpenSpec) CLI at the version pinned
by `OPENSPEC_VERSION` in the [`Makefile`](Makefile). Run from the repository root:

```bash
aqua install
npm install --global --ignore-scripts @fission-ai/openspec@2.0.0
uv sync --locked
make validate
```

Validation covers formatting, Python types and lint, Terraform tests, rendered
Kubernetes manifests, integration tests, configuration security and secret
detection. It does not deploy resources or require cluster credentials.
`make scan-images` separately scans rendered container images from registries.
See [tests and VS Code setup](tests/README.md) for focused checks and formatting.

Use `make validate` explicitly: bare `make` runs ArgoCD bootstrap.

## Working with coding agents

Agents read [`AGENTS.md`](AGENTS.md); Claude Code reaches it through
[`CLAUDE.md`](CLAUDE.md). [`openspec/specs/`](openspec/specs/) states what the
homelab guarantees. A change to a guarantee is proposed, implemented and
archived as an OpenSpec change on its branch before merge.

| Tool | Location | Use |
| --- | --- | --- |
| Skills | [`.agents/skills/`](.agents/skills/) | Repeatable tasks: applications, secrets, DHCP reservations, Terraform plan review, platform syncs, OpenSpec, debugging, PR bodies |
| Hooks | [`.claude/hooks/`](.claude/hooks/) | Deny private files and Terraform applies, ask before live changes, format and lint each edited file |
| Subagents | [`.claude/agents/`](.claude/agents/) | `verifier` runs the checks for a change; `reviewer` applies [`REVIEW.md`](REVIEW.md) and the specs |

Hooks guard against mistakes; they are not a sandbox. Live changes still need
your approval, a reviewed Terraform plan or a manual ArgoCD sync.

## Operations

| Task | Guide |
| --- | --- |
| Bootstrap or update the platform | [Talos patches, Cilium and ArgoCD](docs/security-runbook.md#bootstrap-and-platform-changes) |
| Access services or manage TLS, SSO and storage | [Platform operations](docs/security-runbook.md) |
| Use dashboards, alerts and logs | [Monitoring](system/monitoring/README.md) · [Logging](system/logging/README.md) |
| Seal Kubernetes secrets | [Sealed Secrets Web](system/sealed-secrets-web/README.md) |
| Back up or restore application data | [Application backups](docs/backups.md) |
| Recover cluster state or sealing keys | [Talos/etcd](docs/talos-etcd-recovery.md) · [SealedSecrets](docs/sealed-secrets-recovery.md) |
| Plan and apply Terraform changes | [Terraform and state recovery](terraform/README.md) |
| Configure Houston | [Ansible and host services](infra/ansible/README.md) |
| Manage LANs, DNS, firewall and WAN | [UniFi configuration](terraform/unifi/README.md) · [Network layout](infra/unifi/README.md) |
| Review security exceptions | [Exception register](docs/exception-register.md) |

## Repository layout

| Path | Contents |
| --- | --- |
| [`apps/`](apps/) | Home Assistant, Crafty Controller, n8n and Mosquitto |
| [`system/`](system/) | Kubernetes platform manifests, Helm charts and bootstrap |
| [`openspec/`](openspec/) | Specifications of the homelab's guarantees and in-flight changes |
| [`talos/patches/`](talos/patches/) | Machine configuration patches |
| [`terraform/`](terraform/) | Cloudflare, UniFi and Crafty roots; reusable modules |
| [`infra/ansible/`](infra/ansible/) | Houston host configuration |
| [`infra/unifi/`](infra/unifi/) | Network architecture and WAN operations |
| [`tests/`](tests/) | Configuration and integration tests |
| [`docs/`](docs/) | Platform operations, backups and recovery |

Commit Kubernetes credentials as SealedSecrets. Plaintext credentials, device
backups, Terraform state and generated Talos configuration stay outside Git.

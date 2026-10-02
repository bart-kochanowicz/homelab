# AGENTS.md - Developer Guide for Agentic Coding

This guide provides essential information for AI coding agents working in this homelab repository.

## Project Overview

This is a **Kubernetes homelab infrastructure repository** containing:
- **Terraform configuration** for Cloudflare DNS and R2 backup storage
- **Talos Linux** configuration for cluster nodes
- **Kubernetes manifests** (YAML/Kustomize) for system components
- **ArgoCD** GitOps bootstrap and configuration
- **Docker applications** (crafty-controller, home-assistant)

No TypeScript, Python, or Go application source code is present in this repository.

## Build/Test/Lint Commands

### Terraform
```bash
# Format Terraform files
terraform fmt -recursive

# Validate Terraform configuration
cd terraform && terraform validate

# Plan infrastructure changes
cd terraform && terraform plan -var-file variables.tfvars

# Apply infrastructure changes
cd terraform && terraform apply -var-file variables.tfvars
```

### Kubernetes/System
```bash
# Install system dependencies (Ansible)
make -C system install-ansible

# Install Ansible collections
make -C system install-deps

# Bootstrap ArgoCD and system
make -C system bootstrap

# Clean ArgoCD (with confirmation)
make -C system clean

# Force clean ArgoCD (no confirmation)
make -C system force-clean
```

### Validation Commands
```bash
# Validate YAML syntax
find . -name "*.yaml" -o -name "*.yml" | xargs yamllint

# Validate Kubernetes manifests
kubectl apply --dry-run=client -f <file.yaml>

# Validate Kustomize overlays
kustomize build <path>
```

## Code Style & Organization Guidelines

### Directory Structure
```
homelab/
├── terraform/          # Cloudflare infrastructure as code
│   ├── modules/       # Reusable Terraform modules
│   ├── main.tf        # Main module configuration
│   ├── variables.tf   # Input variables (sensitive data via .tfvars)
│   ├── outputs.tf     # Output values
│   └── backend.tf     # Remote state configuration
├── talos/             # Talos Linux node configurations
│   ├── controlplane.yaml
│   └── worker.yaml
├── system/            # Kubernetes system components
│   ├── bootstrap.yaml # ArgoCD bootstrap playbook
│   ├── argocd/        # ArgoCD Helm values and configs
│   ├── monitoring/    # Prometheus/Grafana setup
│   └── Makefile       # Bootstrap automation
└── apps/              # Application deployments
    ├── crafty-controller/
    └── home-assistant/
```

### Terraform Style
- **Formatting**: Run `terraform fmt` to auto-format
- **Naming**: Use lowercase with underscores for variables/resources
- **Sensitive Data**: Use `sensitive = true` for secrets, store in `.tfvars`
- **Outputs**: Export important values; use `sensitive = true` for secrets
- **Comments**: Add descriptions to all variables and outputs
- **Modules**: Encapsulate reusable infrastructure; path: `./modules/<name>`

### Kubernetes Manifests Style
- **Indentation**: 2 spaces (YAML standard)
- **Naming**: Lowercase with hyphens for resource names
- **Namespaces**: Define explicit namespaces; use `kustomization.yaml` for overlays
- **Labels**: Apply consistent labels for selector identification
- **Order**: Namespace → RBAC → ConfigMap/Secret → Deployment → Service
- **Kustomization**: Use `kustomization.yaml` for managing resources
- **Api Versions**: Use current stable API versions (check `kubectl api-resources`)

### Talos Configuration
- **YAML Structure**: Follow Talos schema; validate before applying
- **Updates**: Use Talos CLI: `talosctl apply-config --nodes <ip>`
- **Secrets**: Keep encryption keys secure; use sealed-secrets for K8s

### Ansible Playbooks
- **Format**: YAML with 2-space indentation
- **Error Handling**: Use `ignore_errors`, `failed_when`, `changed_when`
- **Idempotency**: Tasks should be idempotent where possible
- **Handlers**: Use for service restarts and notifications

### Secrets & Sensitive Data
- **Never commit** secrets to git; use `.gitignore`
- **Use sealed-secrets** for Kubernetes secrets (see `system/sealed-secrets/`)
- **Terraform**: Mark sensitive variables with `sensitive = true`
- **Files**: Store examples as `*.example` (e.g., `backend.tf.example`)
- **Environment**: Use `.tfvars` files (excluded from git)

### Documentation
- **Add comments** to complex or non-obvious configurations
- **Update README** when adding new modules or components
- **Document variables** with `description` field in `.tf` files
- **Link references** to external docs (Talos, Kubernetes, Terraform)

## Important Project-Specific Rules

1. **Application Access**: Application endpoints are private; public Cloudflare Tunnel publication is not part of the desired configuration
2. **ArgoCD Sync**: Changes in `system/argocd/` require bootstrap or manual sync
3. **State Management**: Terraform state is remote (configured in `backend.tf`)
4. **KUBECONFIG**: Set via `KUBECONFIG` environment variable (default: `~/.kube/config`)
5. **Confirmation Prompts**: Destructive operations (clean/force-clean) require confirmation
6. **K8s Version**: Project requires Kubernetes v1.25+
7. **Sealed Secrets**: Always encrypt secrets; never commit plaintext secrets

## File Naming Conventions
- Terraform: `*.tf` files grouped by function (main, variables, outputs, backend)
- Kubernetes: `<component>.yaml` or `<component>-<resource-type>.yaml`
- Kustomization: Always named `kustomization.yaml` (lowercase)
- Configuration: `*.example` for templates; actual values in `.tfvars` or `.env`
- Documentation: `*.md` in component directories

## Error Handling
- **Terraform**: Check `terraform validate` output; review plan before apply
- **Kubernetes**: Verify with `kubectl describe` and `kubectl logs` after deployment
- **Ansible**: Check task output; use `-v` flag for verbose logging
- **Talos**: Use `talosctl` to inspect node status and logs

## Common Tasks

### Adding a New Application
1. Create directory: `apps/<app-name>/`
2. Add Kubernetes manifests (namespace, deployment, service)
3. Create `kustomization.yaml` for resource management
4. Register in ArgoCD ApplicationSet or Application
5. Document in main README

### Adding Infrastructure Module
1. Create `terraform/modules/<module-name>/`
2. Add `main.tf`, `variables.tf`, `outputs.tf`
3. Reference in root `terraform/main.tf`
4. Document variables with descriptions
5. Add example values to `variables.tf` defaults or docs

### Troubleshooting
- ArgoCD out of sync: `kubectl delete application <app> -n argocd` (forces re-sync)
- Sealed secrets issues: Check sealed-secrets pod logs in `kube-system`
- Terraform lock: `rm .terraform.lock.hcl` and re-plan if provider issues
- Talos node issues: Use `talosctl -n <ip> dashboard` for node metrics

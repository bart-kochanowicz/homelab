# gitops-delivery Specification

## Purpose
ArgoCD deploys Kubernetes state from `main`. Applications are generated from
`apps/`; platform components are explicit Applications in `system/argocd/`,
some of which sync only on an operator's request.

## Requirements
### Requirement: Generated applications
Each directory in `apps/` SHALL become an ArgoCD Application in the
`applications` project, deployed to the namespace of the same name with
automated pruning and self-healing.

#### Scenario: New application directory
- **WHEN** `apps/<name>/` with a `kustomization.yaml` merges to main
- **THEN** ArgoCD creates the `<name>` Application targeting namespace `<name>`
- **AND** the namespace already exists from `system/app-namespaces` and is a destination of the `applications` project

### Requirement: Restricted application resources
The `applications` project SHALL deny cluster-scoped resources and allow only
its listed namespaced kinds.

#### Scenario: Application adds a NetworkPolicy
- **WHEN** an `apps/` directory contains a kind outside the project's whitelist
- **THEN** ArgoCD refuses to sync it, and the resource belongs in `system/` instead

### Requirement: Protected namespaces and data
Namespaces and persistent volume claims holding data SHALL be protected from
ArgoCD pruning and deletion.

#### Scenario: Application removed from Git
- **WHEN** an application directory is deleted
- **THEN** its namespace and data PVCs remain until an operator removes them explicitly

### Requirement: Operator-controlled platform syncs
Platform Applications without automated sync SHALL change the cluster only
when an operator syncs them; Cilium SHALL be installed by bootstrap, not ArgoCD.

#### Scenario: Network policy change merges
- **WHEN** a change to `system/network-policies` merges
- **THEN** the cluster keeps its current policies until `network-policies` is synced manually

### Requirement: Self-managed ArgoCD configuration
The `argocd-bootstrap` Application SHALL sync `system/argocd/` automatically
with pruning; `make -C system bootstrap` SHALL install it on a fresh cluster.

#### Scenario: ArgoCD configuration change merges
- **WHEN** a change to `system/argocd/` merges
- **THEN** `argocd-bootstrap` applies it, and prunes Applications whose manifests were removed

#### Scenario: Fresh cluster
- **WHEN** ArgoCD is not installed yet
- **THEN** `make -C system bootstrap` installs ArgoCD and the `argocd-bootstrap` Application

### Requirement: Validated manifests
Every Kustomize directory and Helm chart SHALL render and pass schema,
security and policy checks in `make validate` before merge.

#### Scenario: Invalid manifest
- **WHEN** a change renders a resource that fails kubeconform or kube-linter
- **THEN** validation fails and the pull request cannot merge

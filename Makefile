SHELL := /bin/bash

KUSTOMIZE_DIRS := \
	apps/crafty-controller \
	apps/home-assistant \
	apps/n8n \
	system/app-namespaces \
	system/argocd \
	system/cert-manager-ca \
	system/cloudflared \
	system/local-path-provisioner \
	system/network-policies

.PHONY: default system validate validate-tools validate-format validate-yaml \
	validate-shell validate-kustomize validate-helm validate-kubernetes \
	validate-security validate-permissions

default: system

system:
	make -C system bootstrap

validate: validate-tools validate-format validate-yaml validate-shell \
	validate-kustomize validate-helm validate-kubernetes validate-security \
	validate-permissions

validate-tools:
	@for tool in terraform yamllint shellcheck kubectl helm kubeconform kube-linter trivy gitleaks; do \
		command -v "$$tool" >/dev/null || { echo "missing required tool: $$tool"; exit 1; }; \
	done

validate-format:
	terraform fmt -check -recursive terraform
	terraform -chdir=terraform validate -no-color

validate-yaml:
	find . -type f \( -name '*.yaml' -o -name '*.yml' \) \
		-not -path './.git/*' \
		-not -path './.cache/*' \
		-not -path './.secrets/*' \
		-not -path '*/charts/*' \
		-not -path './terraform/.terraform/*' \
		-not -path './talos/controlplane.yaml' \
		-not -path './talos/worker.yaml' \
		-not -path './talos/talosconfig' \
		-print0 | xargs -0 yamllint -c .yamllint.yaml

validate-shell:
	find . -type f -name '*.sh' \
		-not -path './.git/*' \
		-not -path './.cache/*' \
		-not -path '*/charts/*' \
		-print0 | xargs -0 shellcheck

validate-kustomize:
	@rm -rf .cache/rendered && mkdir -p .cache/rendered
	@for dir in $(KUSTOMIZE_DIRS); do \
		kubectl kustomize "$$dir" > ".cache/rendered/$$(echo "$$dir" | tr / -).yaml"; \
	done
	kubectl kustomize --enable-helm system/monitoring > .cache/rendered/system-monitoring.yaml

validate-helm:
	@helm repo add --force-update jetstack https://charts.jetstack.io >/dev/null
	@helm repo add --force-update cilium https://helm.cilium.io/ >/dev/null
	@helm repo add --force-update sealed-secrets https://bitnami-labs.github.io/sealed-secrets >/dev/null
	@set -e; for spec in \
		system/cert-manager:cert-manager \
		system/cilium:kube-system \
		system/sealed-secrets:sealed-secrets; do \
		dir="$${spec%%:*}"; namespace="$${spec##*:}"; \
		helm dependency build "$$dir" >/dev/null; \
		helm lint "$$dir"; \
		helm template validation "$$dir" --namespace "$$namespace" \
			> ".cache/rendered/helm-$$(basename "$$dir").yaml"; \
	done

validate-kubernetes: validate-kustomize
	kubeconform -strict -summary -ignore-missing-schemas .cache/rendered/*.yaml
	kube-linter lint --config .kube-linter.yaml \
		--ignore-paths '.cache/rendered/helm-cilium.yaml' \
		.cache/rendered/*.yaml
	find .cache/rendered -type f -name '*.yaml' \
		-not -name 'system-monitoring.yaml' \
		-not -name 'helm-cilium.yaml' -print0 | \
		xargs -0 kube-linter lint --do-not-auto-add-defaults \
			--include wildcard-in-rules

validate-security:
	trivy config --exit-code 1 --severity HIGH,CRITICAL \
		--ignorefile .trivyignore.yaml \
		--skip-dirs .git --skip-dirs .terraform --skip-dirs .cache \
		--skip-dirs '**/charts' .
	trivy config --exit-code 1 --severity HIGH,CRITICAL \
		--ignorefile .trivyignore.yaml .cache/rendered
	@rm -rf .cache/gitleaks-tree && mkdir -p .cache/gitleaks-tree
	@git ls-files --cached --others --exclude-standard -z | \
		while IFS= read -r -d '' file; do \
			[[ -f "$$file" ]] && printf '%s\0' "$$file"; \
		done | \
		tar --null -T - -cf - | tar -xf - -C .cache/gitleaks-tree
	cd .cache/gitleaks-tree && \
		gitleaks dir --config "$(CURDIR)/.gitleaks.toml" --redact --verbose .
	gitleaks git --config .gitleaks.toml --redact --verbose --log-opts="--all"

validate-permissions:
	./scripts/check-sensitive-permissions.sh

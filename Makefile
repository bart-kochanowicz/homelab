SHELL := /bin/bash

KUSTOMIZE_DIRS := \
	apps/crafty-controller \
	apps/home-assistant \
	apps/n8n \
	system/app-namespaces \
	system/argocd \
	system/cert-manager-acme \
	system/cert-manager-ca \
	system/gateway-api-crds \
	system/gateways \
	system/local-path-provisioner \
	system/network-policies

.PHONY: default system validate validate-tools validate-format validate-yaml \
	validate-shell validate-kustomize validate-helm validate-kubernetes validate-gateway-api \
	validate-cert-manager validate-cilium-gateways validate-envoy-gateway \
	validate-security validate-terraform-tests validate-terraform-layout validate-workflows

default: system

system:
	make -C system bootstrap

validate: validate-tools validate-format validate-yaml validate-shell \
	validate-kustomize validate-helm validate-kubernetes validate-security \
	validate-terraform-tests validate-workflows

validate-tools:
	@for tool in terraform yamllint shellcheck kubectl helm kubeconform kube-linter trivy gitleaks python3 yq curl; do \
		command -v "$$tool" >/dev/null || { echo "missing required tool: $$tool"; exit 1; }; \
	done

validate-terraform-layout:
	@for file in terraform/*.tf terraform/*.tf.json; do \
		[[ ! -f "$$file" ]] || { echo "Terraform roots must live in terraform/<name>/: $$file"; exit 1; }; \
	done

validate-format: validate-terraform-layout
	terraform fmt -check -recursive terraform
	@for file in terraform/*.tfbackend terraform/*/*.tfvars.example; do \
		terraform fmt -check - < "$$file" || exit 1; \
	done
	terraform -chdir=terraform/cloudflare init -backend=false -input=false -lockfile=readonly
	terraform -chdir=terraform/cloudflare validate -no-color
	terraform -chdir=terraform/unifi init -backend=false -input=false -lockfile=readonly
	terraform -chdir=terraform/unifi validate -no-color
	terraform -chdir=terraform/examples/garage-backend init -backend=false -input=false
	terraform -chdir=terraform/examples/garage-backend validate -no-color
	terraform -chdir=terraform/examples/garage-restore init -backend=false -input=false
	terraform -chdir=terraform/examples/garage-restore validate -no-color

validate-terraform-tests: validate-format
	terraform -chdir=terraform/unifi test -no-color

validate-workflows: validate-gateway-api validate-cilium-gateways validate-envoy-gateway
	python3 -m unittest discover -s tests -v

validate-yaml:
	find . -type f \( -name '*.yaml' -o -name '*.yml' \) \
		-not -path './.git/*' \
		-not -path './.cache/*' \
		-not -path './.secrets/*' \
		-not -path './.backups/*' \
		-not -path './thoughts/*' \
		-not -path '*/charts/*' \
		-not -path '*/.terraform/*' \
		-not -path './talos/controlplane.yaml' \
		-not -path './talos/worker.yaml' \
		-not -path './talos/talosconfig' \
		-print0 | xargs -0 yamllint -c .yamllint.yaml

validate-shell:
	find . -type f -name '*.sh' \
		-not -path './.git/*' \
		-not -path './.cache/*' \
		-not -path './.secrets/*' \
		-not -path './.backups/*' \
		-not -path './thoughts/*' \
		-not -path '*/charts/*' \
		-print0 | xargs -0 shellcheck

validate-kustomize:
	@rm -rf .cache/rendered && mkdir -p .cache/rendered
	@set -e; for dir in $(KUSTOMIZE_DIRS); do \
		kubectl kustomize "$$dir" > ".cache/rendered/$$(echo "$$dir" | tr / -).yaml"; \
	done
	kubectl kustomize --enable-helm system/monitoring > .cache/rendered/system-monitoring.yaml

validate-helm: validate-kustomize
	@set -e; retry() { \
		for attempt in 1 2 3; do \
			"$$@" && return 0; \
			if [ "$$attempt" -lt 3 ]; then \
				echo "retrying: $$*" >&2; \
				sleep "$$((attempt * 2))"; \
			fi; \
		done; \
		return 1; \
	}; \
	retry helm repo add --force-update jetstack https://charts.jetstack.io >/dev/null; \
	retry helm repo add --force-update cilium https://helm.cilium.io/ >/dev/null; \
	retry helm repo add --force-update sealed-secrets https://bitnami.github.io/sealed-secrets >/dev/null; \
	for spec in \
		system/cert-manager:cert-manager \
		system/cilium:kube-system \
		system/envoy-gateway:envoy-gateway-system \
		system/envoy-gateway-crds:argocd \
		system/sealed-secrets:sealed-secrets; do \
		dir="$${spec%%:*}"; namespace="$${spec##*:}"; \
		retry helm dependency build "$$dir" >/dev/null; \
		helm lint "$$dir"; \
		helm template validation "$$dir" --namespace "$$namespace" \
			> ".cache/rendered/helm-$$(basename "$$dir").yaml"; \
	done

validate-gateway-api: validate-kustomize
	@rm -rf .cache/gateway-api-schemas && mkdir -p .cache/gateway-api-schemas
	yq -o=json --split-exp '".cache/gateway-api-schemas/" + .title' \
		'.spec as $$crd | .spec.versions[] | select(.served) | .name as $$version | .schema.openAPIV3Schema | .title = ($$crd.names.singular + "_" + $$version) | (.. | select(has("properties"))).additionalProperties |= (. // false)' \
		.cache/rendered/system-gateway-api-crds.yaml
	yq 'select(.apiVersion | test("^gateway[.]networking[.]k8s[.]io/"))' \
		.cache/rendered/*.yaml > .cache/gateway-api-resources.yaml
	kubeconform -strict -summary \
		-schema-location '.cache/gateway-api-schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' \
		.cache/gateway-api-resources.yaml

validate-cert-manager: validate-helm
	@rm -rf .cache/cert-manager-schemas && mkdir -p .cache/cert-manager-schemas
	yq -o=json --split-exp '".cache/cert-manager-schemas/" + .title' \
		'select(.kind == "CustomResourceDefinition") | .spec as $$crd | .spec.versions[] | select(.served) | .name as $$version | .schema.openAPIV3Schema | .title = ($$crd.names.singular + "_" + $$version) | (.. | select(has("properties"))).additionalProperties |= (. // false)' \
		.cache/rendered/helm-cert-manager.yaml
	yq 'select(.apiVersion | test("^(acme[.])?cert-manager[.]io/"))' \
		.cache/rendered/*.yaml > .cache/cert-manager-resources.yaml
	kubeconform -strict -summary \
		-schema-location '.cache/cert-manager-schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' \
		.cache/cert-manager-resources.yaml

validate-cilium-gateways: validate-kustomize
	@rm -rf .cache/cilium-gateway-crds .cache/cilium-gateway-schemas && \
		mkdir -p .cache/cilium-gateway-crds .cache/cilium-gateway-schemas
	@set -e; version="$$(yq '.dependencies[] | select(.name == "cilium") | .version' system/cilium/Chart.yaml)"; \
	for resource in v2/ciliumloadbalancerippools v2alpha1/ciliuml2announcementpolicies; do \
		curl --fail --silent --show-error --location --retry 3 \
			"https://raw.githubusercontent.com/cilium/cilium/v$$version/pkg/k8s/apis/cilium.io/client/crds/$$resource.yaml" \
			-o ".cache/cilium-gateway-crds/$${resource##*/}.yaml"; \
	done
	yq -o=json --split-exp '".cache/cilium-gateway-schemas/" + .title' \
		'.spec as $$crd | .spec.versions[] | select(.served) | .name as $$version | .schema.openAPIV3Schema | .title = ($$crd.names.singular + "_" + $$version) | (.. | select(has("properties"))).additionalProperties |= (. // false)' \
		.cache/cilium-gateway-crds/*.yaml
	yq 'select(.apiVersion | test("^cilium[.]io/")) | select(.kind == "CiliumLoadBalancerIPPool" or .kind == "CiliumL2AnnouncementPolicy")' \
		.cache/rendered/*.yaml > .cache/cilium-gateway-resources.yaml
	kubeconform -strict -summary \
		-schema-location '.cache/cilium-gateway-schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' \
		.cache/cilium-gateway-resources.yaml

validate-envoy-gateway: validate-helm
	@rm -rf .cache/envoy-gateway-schemas && mkdir -p .cache/envoy-gateway-schemas
	yq -o=json --split-exp '".cache/envoy-gateway-schemas/" + .title' \
		'select(.kind == "CustomResourceDefinition") | .spec as $$crd | .spec.versions[] | select(.served) | .name as $$version | .schema.openAPIV3Schema | .title = ($$crd.names.singular + "_" + $$version) | (.. | select(has("properties"))).additionalProperties |= (. // false)' \
		.cache/rendered/helm-envoy-gateway-crds.yaml
	yq 'select(.apiVersion | test("^gateway[.]envoyproxy[.]io/"))' \
		.cache/rendered/*.yaml > .cache/envoy-gateway-resources.yaml
	kubeconform -strict -summary \
		-schema-location '.cache/envoy-gateway-schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' \
		.cache/envoy-gateway-resources.yaml

validate-kubernetes: validate-kustomize validate-gateway-api validate-cert-manager validate-cilium-gateways validate-envoy-gateway
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
		--skip-dirs .secrets --skip-dirs .backups --skip-dirs thoughts \
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

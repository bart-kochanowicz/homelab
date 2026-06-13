KUBECONFIG ?= ~/.kube/config
NAMESPACE := argocd
RELEASE := argocd
CHART := argo-cd
REPO := https://argoproj.github.io/argo-helm
VERSION := 8.6.3

.PHONY: all install-ansible install-deps bootstrap bootstrap-cilium \
	cilium-preflight cilium-migrate cilium-rollback clean force-clean \
	setup-from-scratch

all: bootstrap

setup-from-scratch: install-ansible install-deps bootstrap-cilium bootstrap
	@echo "✅ Complete setup finished!"

install-ansible:
	@echo "📦 Installing Ansible and dependencies..."
	pip3 install ansible kubernetes

install-deps:
	@echo "📦 Installing Ansible collections..."
	ansible-galaxy collection install -r requirements.yml --force

bootstrap: install-deps
	@echo "🚀 Bootstrapping ArgoCD with Ansible..."
	ansible-playbook bootstrap.yaml -v

bootstrap-cilium:
	helm dependency build cilium
	helm upgrade --install cilium cilium \
		--namespace kube-system --create-namespace --wait --timeout 15m

cilium-preflight:
	../scripts/cilium-migrate.sh

cilium-migrate:
	CONFIRM_CILIUM_MIGRATION=yes ../scripts/cilium-migrate.sh --execute

cilium-rollback:
	CONFIRM_CILIUM_ROLLBACK=yes ../scripts/cilium-rollback.sh

clean:
	@echo "🧹 Cleaning up ArgoCD installation..."
	@echo "⚠️  This will delete ALL ArgoCD resources!"
	@read -p "Type 'yes' to continue: " confirm && [ "$$confirm" = "yes" ]
	@echo "🗑️  Removing Applications..."
	kubectl delete applications --all -n $(NAMESPACE) || true
	kubectl delete applications --all -n default || true
	@echo "🗑️  Removing ApplicationSets..."
	kubectl delete applicationsets --all -n $(NAMESPACE) || true
	@echo "🗑️  Removing ArgoCD Helm release..."
	helm uninstall $(RELEASE) -n $(NAMESPACE) || true
	@echo "🗑️  Removing ArgoCD CRDs..."
	kubectl delete crd applications.argoproj.io appprojects.argoproj.io applicationsets.argoproj.io || true
	@echo "🗑️  Removing ConfigMaps and Secrets..."
	kubectl delete configmap argocd-cm -n $(NAMESPACE) || true
	kubectl delete secret argocd-initial-admin-secret -n $(NAMESPACE) || true
	@echo "🗑️  Removing namespace..."
	kubectl delete namespace $(NAMESPACE) || true
	@echo "✅ Cleanup completed!"

force-clean:
	@echo "💥 FORCE cleaning ArgoCD (no confirmation)..."
	kubectl delete applications --all -n $(NAMESPACE) || true
	kubectl delete applications --all -n default || true
	kubectl delete applicationsets --all -n $(NAMESPACE) || true
	helm uninstall $(RELEASE) -n $(NAMESPACE) || true
	kubectl delete crd applications.argoproj.io appprojects.argoproj.io applicationsets.argoproj.io || true
	kubectl delete configmap argocd-cm -n $(NAMESPACE) || true
	kubectl delete secret argocd-initial-admin-secret -n $(NAMESPACE) || true
	kubectl delete namespace $(NAMESPACE) || true
	@echo "✅ Force cleanup completed!"

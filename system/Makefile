NAMESPACE := argocd
RELEASE := argocd

.PHONY: all install-ansible install-deps bootstrap bootstrap-cilium \
	clean force-clean setup-from-scratch

all: bootstrap

setup-from-scratch: install-ansible install-deps bootstrap-cilium bootstrap

install-ansible:
	pip3 install ansible kubernetes

install-deps:
	ansible-galaxy collection install -r requirements.yml --force

bootstrap: install-deps
	ansible-playbook bootstrap.yaml -v

bootstrap-cilium:
	helm dependency build cilium
	helm upgrade --install cilium cilium \
		--namespace kube-system --create-namespace --wait --timeout 15m

clean:
	@echo "This will delete all ArgoCD resources."
	@read -p "Type 'yes' to continue: " confirm && [ "$$confirm" = "yes" ]
	$(MAKE) force-clean

force-clean:
	kubectl delete applications --all -n $(NAMESPACE) || true
	kubectl delete applications --all -n default || true
	kubectl delete applicationsets --all -n $(NAMESPACE) || true
	helm uninstall $(RELEASE) -n $(NAMESPACE) || true
	kubectl delete crd applications.argoproj.io appprojects.argoproj.io applicationsets.argoproj.io || true
	kubectl delete configmap argocd-cm -n $(NAMESPACE) || true
	kubectl delete secret argocd-initial-admin-secret -n $(NAMESPACE) || true
	kubectl delete namespace $(NAMESPACE) || true

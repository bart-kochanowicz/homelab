"""Check that the guard hook stops private file access and live changes."""

import tempfile
import unittest
from pathlib import Path

from .support import decision


def bash(command: str) -> str:
    return decision("Bash", {"command": command})


class LiveChangeTests(unittest.TestCase):
    def assert_decisions(self, expected: str, commands: list[str]):
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(bash(command), expected)

    def test_terraform_applies_and_destructive_cluster_commands_are_denied(self):
        self.assert_decisions(
            "deny",
            [
                "terraform apply",
                "terraform -chdir=terraform/unifi apply -auto-approve",
                "terraform destroy",
                "make",
                "make -j2",
                "make system",
                "make -C system force-clean",
                "kubectl --context homelab-prod -n n8n delete pvc n8n-data-nvme",
                "kubectl delete namespace home-assistant",
                "kubectl delete ns/n8n",
                "kubectl -n n8n delete pods --all",
                "talosctl -n 10.0.70.12 reset",
                "rm terraform/unifi/.terraform.lock.hcl",
                "git rm terraform/cloudflare/.terraform.lock.hcl",
            ],
        )

    def test_commands_that_change_live_systems_need_confirmation(self):
        self.assert_decisions(
            "ask",
            [
                "make -C system bootstrap",
                "make --directory=system bootstrap-cilium",
                "kubectl apply -f deployment.yaml",
                "kubectl -n n8n rollout restart deployment/n8n",
                "kubectl -n n8n delete pod n8n-0",
                "kubectl exec -n n8n deploy/n8n -- sh",
                "helm upgrade --install cilium cilium -n kube-system",
                "talosctl -n 10.0.70.11 apply-config --file controlplane.yaml",
                "talosctl etcd defrag",
                "cilium upgrade",
                "argocd app sync network-policies",
                "ansible-playbook playbooks/houston.yml --ask-become-pass",
                "gh secret set UNIFI_INFRASTRUCTURE_MACS -R owner/repo",
                "terraform state rm module.reservations.unifi_client.this",
                "terraform import unifi_client.tv 0",
                "terraform force-unlock 1234",
            ],
        )

    def test_checks_and_reads_pass_through(self):
        self.assert_decisions(
            "",
            [
                "make validate",
                "make validate-python PYTHON_TEST_JOBS=1",
                "make format-python",
                "terraform -chdir=terraform/unifi plan",
                "terraform fmt -recursive terraform",
                "terraform state list",
                "kubectl get applications -n argocd",
                "kubectl apply --dry-run=server -f deployment.yaml",
                "helm template validation system/vault",
                "talosctl etcd snapshot db.snapshot",
                "ansible-playbook playbooks/houston.yml --check --diff",
                "gh pr list",
                "git log --oneline | head -5",
                "echo 'unbalanced",
            ],
        )

    def test_wrappers_chains_and_subshells_are_inspected(self):
        self.assertEqual(bash("FOO=1 sudo kubectl delete ns n8n"), "deny")
        self.assertEqual(bash("make validate && terraform apply"), "deny")
        self.assertEqual(
            bash("bash -c 'terraform -chdir=terraform/unifi apply'"), "deny"
        )
        self.assertEqual(bash("echo ready; helm uninstall argocd -n argocd"), "ask")
        self.assertEqual(bash("cd system && make"), "ask")
        self.assertEqual(bash("cd system && make force-clean"), "deny")
        self.assertEqual(bash("kubectl apply -f a.yaml && terraform apply"), "deny")

    def test_wrappers_with_values_and_tool_runners_are_unwrapped(self):
        self.assert_decisions(
            "deny",
            [
                "timeout 600 terraform apply",
                "timeout -s KILL 10m terraform apply",
                "nice -n 10 terraform apply",
                "sudo -u root kubectl delete ns n8n",
                "env -u KUBECONFIG FOO=1 kubectl delete pvc data",
                "aqua exec -- terraform apply",
                "uv run --locked terraform -chdir=terraform/unifi apply",
                "uv run --with ansible -- terraform destroy",
                "bash -lc 'terraform apply'",
                "talosctl -n 10.0.70.12 wipe disk sda",
                "kubectl delete Namespace n8n",
                "kubectl -n n8n delete -l app=n8n pvc",
            ],
        )

    def test_reading_credentials_through_the_shell_needs_confirmation(self):
        self.assert_decisions(
            "ask",
            [
                "kubectl -n n8n get secret n8n -o yaml",
                "kubectl get secrets -A",
                "kubectl get sealedsecret/n8n -n n8n -o json",
                "cat .secrets/terraform/garage.credentials",
                "grep token terraform/unifi/terraform.tfvars",
                "terraform -chdir=terraform/unifi init -migrate-state",
            ],
        )

    def test_read_only_variants_pass_through(self):
        self.assert_decisions(
            "",
            [
                "kubectl -n n8n rollout status deployment/n8n",
                "kubectl -n n8n describe secret n8n",
                "kubectl get applications -n argocd -o wide",
                "make -C tests",
                "uv run --locked pyright",
                "timeout 60 make validate-python",
            ],
        )


class PrivateFileTests(unittest.TestCase):
    def test_private_files_are_denied_for_every_file_tool(self):
        for tool in ("Read", "Edit", "Write"):
            for path in (
                ".secrets/terraform/garage.credentials",
                "terraform/unifi/terraform.tfstate",
                "terraform/unifi/plan.tfplan",
                "talos/controlplane.yaml",
                "talos/talosconfig",
                "infra/unifi/private/leox.txt",
                "system/backups/server.key",
            ):
                with self.subTest(tool=tool, path=path):
                    self.assertEqual(decision(tool, {"file_path": path}), "deny")

    def test_absolute_paths_through_worktree_links_are_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            main_checkout = project / "main"
            (main_checkout / ".secrets").mkdir(parents=True)
            worktree = project / "worktree"
            worktree.mkdir()
            (worktree / ".secrets").symlink_to(main_checkout / ".secrets")
            path = str(worktree / ".secrets" / "token")
            self.assertEqual(decision("Read", {"file_path": path}, worktree), "deny")

    def test_local_provider_inputs_need_confirmation(self):
        self.assertEqual(
            decision("Read", {"file_path": "terraform/unifi/terraform.tfvars"}), "ask"
        )
        self.assertEqual(
            decision("Read", {"file_path": "terraform/unifi/terraform.tfvars.example"}),
            "",
        )

    def test_searches_of_private_paths_are_checked(self):
        self.assertEqual(
            decision("Grep", {"pattern": "token", "path": ".secrets"}), "deny"
        )
        self.assertEqual(
            decision("Glob", {"pattern": "*", "path": "infra/unifi/private"}), "deny"
        )
        self.assertEqual(
            decision(
                "Grep",
                {"pattern": "api_key", "path": "terraform/unifi/terraform.tfvars"},
            ),
            "ask",
        )
        self.assertEqual(decision("Grep", {"pattern": "name", "path": "apps"}), "")

    def test_tracked_files_pass_through(self):
        for path in ("README.md", "system/backups/ca.crt", "talos/patches/dns.yaml"):
            with self.subTest(path=path):
                self.assertEqual(decision("Read", {"file_path": path}), "")


class PlaintextSecretTests(unittest.TestCase):
    SECRET = "apiVersion: v1\nkind: Secret\nmetadata:\n  name: token\nstringData:\n  token: value\n"
    SEALED = (
        "apiVersion: bitnami.com/v1alpha1\nkind: SealedSecret\nmetadata:\n  name: token\n"
        "spec:\n  encryptedData:\n    token: AgB\n  template:\n    type: Opaque\n"
    )

    def test_writing_a_plaintext_secret_is_denied(self):
        self.assertEqual(
            decision(
                "Write", {"file_path": "apps/n8n/secret.yaml", "content": self.SECRET}
            ),
            "deny",
        )
        documents = (
            "apiVersion: v1\nkind: ConfigMap\ndata:\n  a: b\n---\n" + self.SECRET
        )
        self.assertEqual(
            decision("Write", {"file_path": "apps/n8n/all.yaml", "content": documents}),
            "deny",
        )

    def test_an_edit_that_turns_a_file_into_a_secret_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            target = project / "secret.yaml"
            target.write_text(
                "apiVersion: v1\nkind: Secret\nmetadata:\n  name: token\n"
            )
            edit = {
                "file_path": str(target),
                "old_string": "  name: token\n",
                "new_string": "  name: token\ndata:\n  token: dmFsdWU=\n",
            }
            self.assertEqual(decision("Edit", edit, project), "deny")

    def test_sealed_secrets_and_config_maps_are_allowed(self):
        self.assertEqual(
            decision(
                "Write",
                {"file_path": "apps/n8n/sealed-secret.yaml", "content": self.SEALED},
            ),
            "",
        )
        config = "apiVersion: v1\nkind: ConfigMap\ndata:\n  a: b\n"
        self.assertEqual(
            decision(
                "Write", {"file_path": "apps/n8n/configmap.yaml", "content": config}
            ),
            "",
        )


if __name__ == "__main__":
    unittest.main()

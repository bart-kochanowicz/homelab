---
name: terraform-plan-review
description: Review a Terraform plan for terraform/unifi, cloudflare or crafty before the user approves it, locally or from the GitHub Actions logs. Use when a Terraform change is merged or about to be, when the user shares plan output, or when a plan shows unexpected changes.
---

# Terraform plan review

Applies happen only in GitHub Actions after the user approves a saved plan;
local sessions plan with read-only Garage access (`terraform/LOCAL_PLAN.md`).
The agent's job is to say whether the plan matches the intended change.

## Get the plan

- **Actions**: after `main` validation succeeds, the Terraform workflow plans
  each root on Houston. Ask the user for the run link or the plan log section;
  the logs live in the private automation repository.
- **Local**: the user opens the Houston tunnel from `terraform/LOCAL_PLAN.md`
  in their own terminal, then runs `terraform plan` in the root. Planning reads
  provider credentials from the ignored `terraform.tfvars`; keep its contents
  out of the conversation.

## Review

Work from the change's diff: list every resource the diff should touch, then
account for every line of the plan summary against that list.

1. **Counts.** `N to add, N to change, N to destroy, N to import` matches the
   intended change exactly. Any extra resource is a finding.
2. **Destroys and replacements.** Every `-` and `-/+` names a resource the
   change removes or must recreate. For UniFi reservations,
   `skip_forget_on_destroy` makes a destroy a state-only removal; confirm it
   removes no other reservation.
3. **Imports.** `import` blocks adopt existing objects; the plan shows an
   import, not a create, with no attribute drift after it.
4. **Drift.** Changes the diff does not explain mean someone edited the
   controller or Cloudflare by hand. Stop and ask the user which side is right.
5. **Firewall and DNS.** Rules stay least-privilege (specific IPs, ports and
   protocols); no record publishes a private hostname to Cloudflare.
6. **Sensitive values.** They show as `(sensitive value)`. A credential
   printed in clear is a bug to fix before approval.

## Report

Give the verdict first: approve, or do not approve and why. List each
unexpected or risky change with its resource address. If the plan is stale
(source or state changed, or it expired), it needs a new plan and approval.

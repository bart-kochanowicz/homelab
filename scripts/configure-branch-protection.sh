#!/usr/bin/env bash
set -euo pipefail

repo="${GITHUB_REPOSITORY:-bart-kochanowicz/homelab}"

if [[ "${CONFIRM_BRANCH_PROTECTION:-}" != "yes" ]]; then
  echo "Set CONFIRM_BRANCH_PROTECTION=yes after the Validate workflow succeeds on main." >&2
  exit 1
fi

gh api --method PUT "repos/${repo}/branches/main/protection" \
  --input - <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["validate"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_conversation_resolution": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_linear_history": true,
  "lock_branch": false,
  "allow_fork_syncing": false
}
EOF

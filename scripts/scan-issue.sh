#!/usr/bin/env bash
# Keep one open issue per failing scheduled scan.
#
#   scan-issue.sh open TITLE BODY_FILE RUN_URL   open the issue, or update it and comment
#   scan-issue.sh close TITLE RUN_URL            close the open issue, if any
#
# Needs gh with GH_TOKEN allowed to write issues, and jq.
set -euo pipefail

label=scan-failure

usage() {
  sed -n '2,7p' "$0" >&2
  exit 2
}

open_issue() {
  gh issue list --state open --label "$label" --limit 100 --json number,title |
    jq -r --arg title "$1" 'map(select(.title == $title)) | first | .number // empty'
}

[[ $# -ge 1 ]] || usage
case "$1" in
  open)
    [[ $# -eq 4 ]] || usage
    title=$2 body=$3 run=$4
    number=$(open_issue "$title")
    if [[ -z "$number" ]]; then
      gh label create "$label" --color d73a4a \
        --description "A scheduled security scan fails" --force
      gh issue create --title "$title" --label "$label" --body-file "$body"
    else
      gh issue edit "$number" --body-file "$body"
      gh issue comment "$number" --body "The scan failed again in $run."
    fi
    ;;
  close)
    [[ $# -eq 3 ]] || usage
    title=$2 run=$3
    number=$(open_issue "$title")
    if [[ -n "$number" ]]; then
      gh issue close "$number" --comment "The scan passes again in $run."
    fi
    ;;
  *)
    usage
    ;;
esac

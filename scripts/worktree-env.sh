#!/usr/bin/env bash
# Link the ignored local files listed in .worktreeinclude from the main checkout
# into this worktree, so every worktree reads and edits the same copy.
set -euo pipefail

fail() {
  printf '%s\n' "$*" >&2
  exit 1
}

worktree=$(git rev-parse --show-toplevel)
main=$(dirname "$(git -C "$worktree" rev-parse --path-format=absolute --git-common-dir)")
[[ $worktree != "$main" ]] || exit 0
[[ -f $worktree/.worktreeinclude ]] || fail 'Missing .worktreeinclude.'

while IFS= read -r line || [[ -n $line ]]; do
  path=${line%%#*}
  path=${path//[[:space:]]/}
  path=${path#/}
  path=${path%/}
  [[ -n $path ]] || continue
  [[ $path != *[\*\?\[]* && $path != *..* ]] || fail "Use exact paths in .worktreeinclude: $line"
  git -C "$worktree" check-ignore -q "$path" || fail "Not ignored by Git: $path"

  source=$main/$path
  target=$worktree/$path
  if [[ ! -e $source ]]; then
    printf 'skip %s: missing in %s\n' "$path" "$main"
  elif [[ -L $target && $(readlink "$target") == "$source" ]]; then
    continue
  elif [[ -e $target || -L $target ]]; then
    printf 'keep %s: already exists in this worktree\n' "$path" >&2
  else
    mkdir -p "$(dirname "$target")"
    ln -s "$source" "$target"
    printf 'linked %s\n' "$path"
  fi
done < "$worktree/.worktreeinclude"

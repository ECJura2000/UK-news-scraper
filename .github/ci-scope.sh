#!/usr/bin/env bash
# Conservative routing: only explicitly safe paths qualify for a lighter run.
set -euo pipefail
kind() {
  case "$1" in
    README.md|CHANGELOG.md|ARCHITECTURE.md|PERFORMANCE.md|PROJECT_REPORT.md|CONTRIBUTING.md|NOTICE.md|CI.md|docs/*.md) echo docs ;;
    tests/test_*.py|tests/conftest.py) echo python-tests ;;
    *) echo full ;;
  esac
}
scope() {
  local mode=docs k p
  if [[ $# -eq 0 ]]; then echo full; return; fi
  for p in "$@"; do
    k=$(kind "$p")
    if [[ $k == full ]]; then echo full; return; fi
    if [[ $k != docs ]]; then
      if [[ $mode != docs && $mode != "$k" ]]; then echo full; return; fi
      mode=$k
    fi
  done
  echo "$mode"
}
if [[ ${1:-} == --self-test ]]; then
  [[ $(scope README.md docs/DEMO.md) == docs ]]
  [[ $(scope README.md tests/test_app_service.py) == python-tests ]]
  [[ $(scope README.md Cargo.lock) == full ]]
  [[ $(scope .github/ci-scope.sh) == full ]]
  [[ $(scope) == full ]]
  exit 0
fi
mode=full
range=
case "${GITHUB_EVENT_NAME:-}" in
  pull_request) range="${CI_BASE:-}...${CI_HEAD:-}" ;;
  push) if [[ "${GITHUB_REF:-}" != refs/tags/* ]]; then range="${CI_BEFORE:-}..${CI_HEAD:-}"; fi ;;
esac
if [[ $range =~ ^[0-9a-f]{40}\.\.\.?[0-9a-f]{40}$ && $range != *0000000000000000000000000000000000000000* ]]; then
  temp=$(mktemp)
  trap 'rm -f "$temp"' EXIT
  if git diff --no-renames --name-only -z "$range" -- > "$temp"; then
    paths=()
    while IFS= read -r -d '' p; do paths+=("$p"); done < "$temp"
    mode=$(scope "${paths[@]}")
    if [[ $mode == docs ]]; then
      git -c core.whitespace=-blank-at-eol diff --check "$range" --
    fi
  fi
fi
printf 'mode=%s\n' "$mode" >> "$GITHUB_OUTPUT"
printf 'CI scope: %s\n' "$mode"

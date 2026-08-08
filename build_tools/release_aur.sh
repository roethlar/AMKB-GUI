#!/usr/bin/env bash
# AUR release helper for this repository.
# Full process: packaging/aur/PROCESS.md
#
# Usage:
#   ./build_tools/release_aur.sh prepare [--version X.Y.Z]
#   ./build_tools/release_aur.sh push    [--aur-git PATH]
#   ./build_tools/release_aur.sh all     # prepare then push (needs AUR SSH)
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is required (https://docs.astral.sh/uv/)" >&2
  exit 1
fi

cmd="${1:-}"
if [[ -z "$cmd" || "$cmd" == "-h" || "$cmd" == "--help" ]]; then
  cat <<'EOF'
AUR release process (maintainer). See packaging/aur/PROCESS.md

  ./build_tools/release_aur.sh prepare [--version X.Y.Z]
      Download SHA256SUMS for the published GitHub Release and write
      dist/package-managers/am-configurator-bin/

  ./build_tools/release_aur.sh push [--aur-git PATH]
      Sync that tree into the AUR git clone, commit, and push.
      Requires: ssh -T aur@aur.archlinux.org

  ./build_tools/release_aur.sh all [--version X.Y.Z]
      prepare then push.

Not for every CI build — only after a public GitHub Release exists.
EOF
  exit 0
fi

shift || true
extra=("$@")

case "$cmd" in
  prepare)
    exec uv run --frozen python -m build_tools.package_managers prepare-aur "${extra[@]}"
    ;;
  push)
    exec uv run --frozen python -m build_tools.package_managers push-aur "${extra[@]}"
    ;;
  all)
    uv run --frozen python -m build_tools.package_managers prepare-aur "${extra[@]}"
    exec uv run --frozen python -m build_tools.package_managers push-aur
    ;;
  *)
    echo "error: unknown command: $cmd (try: prepare | push | all)" >&2
    exit 1
    ;;
esac

#!/usr/bin/env bash
# AUR release helper for this repository.
# Full process: packaging/aur/PROCESS.md
#
# Usage:
#   ./build_tools/release_aur.sh prepare [--version X.Y.Z]
#   ./build_tools/release_aur.sh push    [--aur-git PATH]
#   ./build_tools/release_aur.sh all     # prepare then push (needs AUR SSH)
#
# Needs Python 3 only. Prefers `uv run --frozen` when uv is installed; otherwise
# runs `python3 -m build_tools.package_managers` (stdlib + this repo — enough
# for prepare-aur / push-aur).
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

run_pm() {
  # Prefer the repo's locked env when uv is present; fall back to system Python.
  if command -v uv >/dev/null 2>&1; then
    uv run --frozen python -m build_tools.package_managers "$@"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHONPATH="$root${PYTHONPATH:+:$PYTHONPATH}" python3 -m build_tools.package_managers "$@"
  else
    echo "error: need uv or python3 on PATH" >&2
    exit 1
  fi
}

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
Requires python3 (or uv). No full project venv required for prepare/push.
EOF
  exit 0
fi

shift || true
extra=("$@")

case "$cmd" in
  prepare)
    run_pm prepare-aur "${extra[@]}"
    ;;
  push)
    run_pm push-aur "${extra[@]}"
    ;;
  all)
    run_pm prepare-aur "${extra[@]}"
    run_pm push-aur
    ;;
  *)
    echo "error: unknown command: $cmd (try: prepare | push | all)" >&2
    exit 1
    ;;
esac

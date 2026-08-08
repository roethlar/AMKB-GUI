#!/usr/bin/env bash
# Flatpak release helper. See packaging/flatpak/PROCESS.md
#
#   ./build_tools/release_flatpak.sh prepare [--version X.Y.Z]
#   ./build_tools/release_flatpak.sh build
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

run_pm() {
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
Flatpak release (maintainer). packaging/flatpak/PROCESS.md

  ./build_tools/release_flatpak.sh prepare [--version X.Y.Z]
      Download release digests/size; write dist/package-managers/flatpak/

  ./build_tools/release_flatpak.sh build
      flatpak-builder --user --install --force-clean (needs flatpak-builder)

Only after a public GitHub Release exists.
EOF
  exit 0
fi

shift || true
extra=("$@")

case "$cmd" in
  prepare)
    run_pm prepare-flatpak "${extra[@]}"
    ;;
  build)
    dir="${FLATPAK_OUT:-$root/dist/package-managers/flatpak}"
    manifest="$dir/io.github.roethlar.AMConfigurator.yml"
    if [[ ! -f "$manifest" ]]; then
      echo "error: missing $manifest — run prepare first" >&2
      exit 1
    fi
    if ! command -v flatpak-builder >/dev/null 2>&1; then
      echo "error: flatpak-builder not on PATH" >&2
      exit 1
    fi
    exec flatpak-builder --user --install --force-clean "$dir/build" "$manifest"
    ;;
  *)
    echo "error: unknown command: $cmd (try: prepare | build)" >&2
    exit 1
    ;;
esac

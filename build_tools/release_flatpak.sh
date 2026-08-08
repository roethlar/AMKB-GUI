#!/usr/bin/env bash
# Flatpak release helper. See packaging/flatpak/PROCESS.md
#
#   ./build_tools/release_flatpak.sh              # prepare + ensure deps + build
#   ./build_tools/release_flatpak.sh prepare [--version X.Y.Z]
#   ./build_tools/release_flatpak.sh build
#   ./build_tools/release_flatpak.sh smoke
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

APP_ID="io.github.roethlar.AMConfigurator"
RUNTIME_REF="org.freedesktop.Platform//24.08"
SDK_REF="org.freedesktop.Sdk//24.08"
FLATPAK_DIR="${FLATPAK_OUT:-$root/dist/package-managers/flatpak}"
MANIFEST="$FLATPAK_DIR/${APP_ID}.yml"

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

ensure_flatpak_builder() {
  if command -v flatpak-builder >/dev/null 2>&1; then
    return 0
  fi
  echo "error: flatpak-builder not on PATH." >&2
  echo "  Arch: sudo pacman -S flatpak-builder" >&2
  echo "  Fedora: sudo dnf install flatpak-builder" >&2
  echo "  Debian/Ubuntu: sudo apt install flatpak-builder" >&2
  exit 1
}

ensure_flatpak() {
  if command -v flatpak >/dev/null 2>&1; then
    return 0
  fi
  echo "error: flatpak not on PATH (install the flatpak package)." >&2
  exit 1
}

# Install Flathub (user) + Platform/Sdk so the next build does not fail with
# "Sdk not installed". Idempotent.
ensure_runtime() {
  ensure_flatpak
  if ! flatpak remotes --user 2>/dev/null | awk '{print $1}' | grep -qx flathub; then
    echo "Adding user Flathub remote…"
    flatpak remote-add --if-not-exists --user flathub \
      https://dl.flathub.org/repo/flathub.flatpakrepo
  fi
  # Prefer --user so polkit is not required for deploy.
  local need=()
  if ! flatpak info --user "$RUNTIME_REF" &>/dev/null \
    && ! flatpak info "$RUNTIME_REF" &>/dev/null; then
    need+=("$RUNTIME_REF")
  fi
  if ! flatpak info --user "$SDK_REF" &>/dev/null \
    && ! flatpak info "$SDK_REF" &>/dev/null; then
    need+=("$SDK_REF")
  fi
  if ((${#need[@]})); then
    echo "Installing Flatpak runtime/SDK (user): ${need[*]}"
    flatpak install -y --user flathub "${need[@]}"
  fi
}

do_prepare() {
  # Allow re-run after a previous build left dist/package-managers/flatpak/build
  rm -rf "$FLATPAK_DIR/build"
  run_pm prepare-flatpak "$@"
}

do_build() {
  ensure_flatpak_builder
  ensure_runtime
  if [[ ! -f "$MANIFEST" ]]; then
    echo "error: missing $MANIFEST — run prepare first (or use default 'all')" >&2
    exit 1
  fi
  # Drop builder cache when sources/scripts change between iterations.
  rm -rf "$root/.flatpak-builder"
  flatpak-builder --user --install --force-clean "$FLATPAK_DIR/build" "$MANIFEST"
  echo "Installed: flatpak run $APP_ID"
}

do_smoke() {
  ensure_flatpak
  flatpak run "$APP_ID" --smoke-test
}

cmd="${1:-all}"
if [[ "$cmd" == "-h" || "$cmd" == "--help" ]]; then
  cat <<'EOF'
Flatpak release (maintainer). packaging/flatpak/PROCESS.md

  ./build_tools/release_flatpak.sh
  ./build_tools/release_flatpak.sh all [--version X.Y.Z]
      prepare + install Platform/Sdk if needed + build + smoke-test

  ./build_tools/release_flatpak.sh prepare [--version X.Y.Z]
  ./build_tools/release_flatpak.sh build
  ./build_tools/release_flatpak.sh smoke

One-time distro package still required once: flatpak-builder
(e.g. sudo pacman -S flatpak-builder). Runtime/SDK are installed for you.
EOF
  exit 0
fi

if [[ "$cmd" == "all" || "$cmd" == "prepare" || "$cmd" == "build" || "$cmd" == "smoke" ]]; then
  shift || true
fi
extra=("$@")

case "$cmd" in
  prepare)
    do_prepare "${extra[@]}"
    ;;
  build)
    do_build
    ;;
  smoke)
    do_smoke
    ;;
  all)
    do_prepare "${extra[@]}"
    do_build
    do_smoke
    ;;
  *)
    # Bare flags like --version: treat as all
    if [[ "$cmd" == --* ]]; then
      do_prepare "$cmd" "${extra[@]}"
      do_build
      do_smoke
    else
      echo "error: unknown command: $cmd (try: all | prepare | build | smoke)" >&2
      exit 1
    fi
    ;;
esac

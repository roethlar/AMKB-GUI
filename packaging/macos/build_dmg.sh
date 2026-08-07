#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$project_root"

app_path="${1:-dist/AM Configurator.app}"
if [[ ! -d "$app_path" ]]; then
  echo "macOS app bundle not found: $app_path" >&2
  exit 1
fi

# A release build passes a real Developer ID through APPLE_SIGNING_IDENTITY —
# the same spelling as the CI secret, so no second name has to be kept in sync.
# A missing secret arrives as an empty-but-defined variable, so the test must be
# for a non-empty value, never for mere definition. PyInstaller ad-hoc signs
# every nested Mach-O file it collects, and notarization refuses a bundle whose
# nested code is not Developer ID signed under the hardened runtime, so the
# identity path has to re-sign the bundle inside-out with --deep. Without the
# identity the bundle keeps its deterministic ad-hoc signature: bundle
# integrity, no publisher trust.
if [[ -n "${APPLE_SIGNING_IDENTITY:-}" ]]; then
  codesign --force --deep --options runtime --timestamp \
    --sign "$APPLE_SIGNING_IDENTITY" "$app_path"
else
  echo "note: APPLE_SIGNING_IDENTITY is unset; $app_path is ad-hoc signed" >&2
  codesign --force --sign - "$app_path"
fi
codesign --verify --deep --strict "$app_path"

artifact_name="$(uv run --frozen python build_tools/release_info.py artifact macos)"
output_path="$project_root/dist/$artifact_name"
staging_dir="$(mktemp -d "${TMPDIR:-/tmp}/am-configurator-dmg.XXXXXX")"
mount_dir="$(mktemp -d "${TMPDIR:-/tmp}/am-configurator-mount.XXXXXX")"
mounted=0

# macOS frequently still holds the volume for a moment after the smoke-test
# process exits, so a single detach loses a race and reports "Resource busy".
# Retry with backoff, then force. Detaching is cleanup: the image has already
# been verified and smoke-tested by this point, so a stubborn mount must not
# fail the build, but it must never be followed by rm -rf over a live mount.
detach_mount() {
  local attempt
  for attempt in 1 2 3 4 5; do
    if hdiutil detach "$mount_dir" -quiet 2>/dev/null; then
      mounted=0
      return 0
    fi
    sleep "$attempt"
  done
  if hdiutil detach "$mount_dir" -force -quiet 2>/dev/null; then
    mounted=0
    return 0
  fi
  return 1
}

cleanup() {
  if [[ "$mounted" == 1 ]]; then
    detach_mount || echo "warning: could not detach $mount_dir" >&2
  fi
  rm -rf "$staging_dir"
  if [[ "$mounted" == 0 ]]; then
    rm -rf "$mount_dir"
  fi
}
trap cleanup EXIT

ditto "$app_path" "$staging_dir/AM Configurator.app"
ln -s /Applications "$staging_dir/Applications"
rm -f "$output_path"
hdiutil create \
  -volname "AM Configurator" \
  -srcfolder "$staging_dir" \
  -format UDZO \
  -ov \
  "$output_path"
hdiutil verify "$output_path"
hdiutil attach "$output_path" -readonly -nobrowse -mountpoint "$mount_dir" -quiet
mounted=1
"$mount_dir/AM Configurator.app/Contents/MacOS/AM Configurator" --smoke-test
detach_mount || echo "warning: could not detach $mount_dir" >&2

echo "$output_path"

#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$project_root"

app_path="${1:-dist/AM Configurator.app}"
if [[ ! -d "$app_path" ]]; then
  echo "macOS app bundle not found: $app_path" >&2
  exit 1
fi

# PyInstaller ad-hoc signs Mach-O binaries while assembling the .app, which
# changes the prepared FFmpeg hash. Re-attest those final bytes, then refresh
# only the outer app seal; the already signed nested executable is unchanged.
uv run --frozen python -m build_tools.finalize_ffmpeg_bundle "$app_path"
codesign --force --sign - "$app_path"
codesign --verify --deep --strict "$app_path"

artifact_name="$(uv run --frozen python build_tools/release_info.py artifact macos)"
output_path="$project_root/dist/$artifact_name"
staging_dir="$(mktemp -d "${TMPDIR:-/tmp}/am-configurator-dmg.XXXXXX")"
mount_dir="$(mktemp -d "${TMPDIR:-/tmp}/am-configurator-mount.XXXXXX")"
mounted=0

cleanup() {
  if [[ "$mounted" == 1 ]]; then
    hdiutil detach "$mount_dir" -quiet || true
  fi
  rm -rf "$staging_dir" "$mount_dir"
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
hdiutil detach "$mount_dir" -quiet
mounted=0

echo "$output_path"

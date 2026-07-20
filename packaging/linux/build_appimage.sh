#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$project_root"

bundle_path="${1:-dist/AM Configurator}"
executable="$bundle_path/AM Configurator"
if [[ ! -x "$executable" ]]; then
  echo "Linux application bundle not found: $executable" >&2
  exit 1
fi

arch="$(uv run --frozen python build_tools/release_info.py arch)"
case "$arch" in
  x86_64) checksum="a6d71e2b6cd66f8e8d16c37ad164658985e0cf5fcaa950c90a482890cb9d13e0" ;;
  aarch64) checksum="1b00524ba8c6b678dc15ef88a5c25ec24def36cdfc7e3abb32ddcd068e8007fe" ;;
  i686) checksum="ba04b9ecb2869993173bd38516dbafcfbe3064aca942500e94e7a3c3c2ea578d" ;;
  armhf) checksum="32aeca26db15a7d029b76adb8d5836f98acbf4a37b2a3101758b094f721e4b67" ;;
esac

tool_dir="$project_root/build/appimage-tools"
tool_path="$tool_dir/appimagetool-$arch.AppImage"
tool_url="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$arch.AppImage"
mkdir -p "$tool_dir"
if [[ ! -f "$tool_path" ]] || ! printf '%s  %s\n' "$checksum" "$tool_path" | sha256sum --check --status; then
  rm -f "$tool_path"
  curl --fail --location --retry 3 --output "$tool_path" "$tool_url"
fi
printf '%s  %s\n' "$checksum" "$tool_path" | sha256sum --check --status
chmod +x "$tool_path"

app_dir="$project_root/build/AM Configurator.AppDir"
rm -rf "$app_dir"
mkdir -p \
  "$app_dir/usr/lib/am-configurator" \
  "$app_dir/usr/share/applications" \
  "$app_dir/usr/share/icons/hicolor/512x512/apps"
cp -a "$bundle_path/." "$app_dir/usr/lib/am-configurator/"
install -m 0755 packaging/linux/AppRun "$app_dir/AppRun"
install -m 0644 packaging/linux/am-configurator.desktop "$app_dir/am-configurator.desktop"
install -m 0644 packaging/linux/am-configurator.desktop "$app_dir/usr/share/applications/am-configurator.desktop"
install -m 0644 assets/am-configurator-512.png "$app_dir/am-configurator.png"
install -m 0644 assets/am-configurator-512.png "$app_dir/usr/share/icons/hicolor/512x512/apps/am-configurator.png"
ln -s am-configurator.png "$app_dir/.DirIcon"

artifact_name="$(uv run --frozen python build_tools/release_info.py artifact linux)"
output_path="$project_root/dist/$artifact_name"
rm -f "$output_path"
ARCH="$arch" APPIMAGE_EXTRACT_AND_RUN=1 "$tool_path" "$app_dir" "$output_path"
chmod +x "$output_path"
APPIMAGE_EXTRACT_AND_RUN=1 "$output_path" --smoke-test

echo "$output_path"

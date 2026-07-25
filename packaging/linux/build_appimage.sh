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

appimagetool_version="1.9.1"
arch="$(uv run --frozen python build_tools/release_info.py arch)"
case "$arch" in
  x86_64) checksum="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0" ;;
  aarch64) checksum="f0837e7448a0c1e4e650a93bb3e85802546e60654ef287576f46c71c126a9158" ;;
  i686) checksum="7ad9ff47c203aae0149b18f6df9e3018b2e2f470ea644a0413e3ded39e9e3bdb" ;;
  armhf) checksum="42b61cba5495d8aaf418a5c9a015a49b85ad92efabcbd3c341f1540440e4e23d" ;;
  *)
    echo "Unsupported appimagetool architecture: $arch" >&2
    exit 1
    ;;
esac

tool_dir="$project_root/build/appimage-tools/$appimagetool_version"
tool_path="$tool_dir/appimagetool-$arch-$checksum.AppImage"
tool_url="https://github.com/AppImage/appimagetool/releases/download/$appimagetool_version/appimagetool-$arch.AppImage"
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

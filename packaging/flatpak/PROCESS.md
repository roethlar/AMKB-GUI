# Flatpak release process

Maintainer-only. App id: `io.github.roethlar.AMConfigurator`.

Embeds the **published Linux AppImage** from GitHub Releases (build-time
download + extract).

## Remember this

**Once per machine** (distro package):

```sh
sudo pacman -S flatpak-builder   # Arch; use apt/dnf equivalent elsewhere
```

**Every public release** (from the app repo):

```sh
./build_tools/release_flatpak.sh
# or pin a version:
./build_tools/release_flatpak.sh all --version 0.1.68
```

That single command:

1. Prepares the manifest from the GitHub Release digests  
2. Adds user Flathub + installs Platform/Sdk 24.08 if missing  
3. Builds and installs the Flatpak  
4. Runs `--smoke-test`

Run the app:

```sh
flatpak run io.github.roethlar.AMConfigurator
```

## Flathub

Separate PR after local install works. Do not document a Flathub install
command until that listing is live.

## Neon 80 udev

Flatpak cannot install host udev rules. See `README-udev.txt` in the prepared
tree and `docs/neon-80-linux.md`.

## Implementation

| Piece | Location |
|---|---|
| one-shot script | `build_tools/release_flatpak.sh` |
| prepare logic | `build_tools/package_managers/release_flatpak.py` |
| manifest | `build_tools/package_managers/flatpak.py` |

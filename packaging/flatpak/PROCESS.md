# Flatpak release process

Maintainer-only. App id: `io.github.roethlar.AMConfigurator`.

Installs the **published Linux AppImage** from GitHub Releases (same bytes as
the release asset). AUR is parked separately.

## Every public release

From the application repo root (needs network to GitHub):

```sh
./build_tools/release_flatpak.sh prepare
# optional: --version 0.1.68
```

Writes `dist/package-managers/flatpak/`.

On a machine with **flatpak-builder**:

```sh
./build_tools/release_flatpak.sh build
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
| prepare | `build_tools/package_managers/release_flatpak.py` |
| manifest | `build_tools/package_managers/flatpak.py` |
| CLI / script | `prepare-flatpak` / `release_flatpak.sh` |

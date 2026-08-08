# AUR release process (`am-configurator-bin`)

Maintainer-only. End users install with an AUR helper after the package exists;
they do not run these commands.

No agent is required. Run this after every **public GitHub Release** that
should appear on the AUR (not after every CI build).

## One-time setup (per machine that will `git push`)

1. AUR account (this project uses `roethlar`).
2. That machine’s SSH **public** key on https://aur.archlinux.org/account/
3. Prove SSH:

   ```sh
   ssh -T aur@aur.archlinux.org
   # expect: Welcome to AUR, <user>!
   ```

4. Optional: set a stable clone path:

   ```sh
   export AUR_GIT=~/aur/am-configurator-bin
   ```

## Every public release

From the **application repo** root (Mac or Linux; needs network to GitHub).
Either the shell wrapper or the Python module is fine — same thing.

```sh
# Version defaults to am_configurator/_version.py — pass --version if needed.
./build_tools/release_aur.sh prepare
# equivalent:
#   uv run --frozen python -m build_tools.package_managers prepare-aur
```

That downloads `SHA256SUMS.txt` for the release and writes:

`dist/package-managers/am-configurator-bin/`  
(PKGBUILD, .SRCINFO, desktop, icon, udev, wrapper, .install)

On a host with **AUR SSH** (Arch is fine; `makepkg` optional):

```sh
# Optional local proof:
#   cd dist/package-managers/am-configurator-bin && makepkg -f

./build_tools/release_aur.sh push
# equivalent:
#   uv run --frozen python -m build_tools.package_managers push-aur
```

Or one shot when AUR SSH works on the same machine:

```sh
./build_tools/release_aur.sh all
```

`push` clones `ssh://aur@aur.archlinux.org/am-configurator-bin.git` into
`$AUR_GIT` or `~/aur/am-configurator-bin` if needed, copies the package files,
commits `am-configurator-bin <version>-1`, and pushes.

If the package tree already lives only on another machine, copy
`dist/package-managers/am-configurator-bin` there first, then:

```sh
./build_tools/release_aur.sh push --package-dir /path/to/am-configurator-bin
# or:
uv run --frozen python -m build_tools.package_managers push-aur \
  --package-dir /path/to/am-configurator-bin
```

## What you do **not** do

- Rebuild the AppImage here — use the GitHub Release asset.
- Hand-edit sha256sums — regenerate with `prepare-aur`.
- Run this on every desktop CI build — only when a version is published.
- Advertise the AUR command in the README until `push-aur` has succeeded and
  https://aur.archlinux.org/packages/am-configurator-bin exists.

## Low-level (tests / offline)

```sh
uv run --frozen python -m build_tools.package_managers aur \
  --sums /path/to/SHA256SUMS.txt \
  --out dist/package-managers/am-configurator-bin
```

## Implementation

| Piece | Location |
|---|---|
| prepare + push | `build_tools/package_managers/release_aur.py` |
| CLI | `python -m build_tools.package_managers …` |
| PKGBUILD content | `build_tools/package_managers/aur.py` |
| Digests / URLs | `build_tools/package_managers/common.py` |

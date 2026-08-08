# Package-manager distribution

**Status:** Approved for implementation through AUR P1 (slices S0–S3). D1a,
D1b (option A), and D2 (identifiers) recorded 2026-08-08. Flatpak remains the
next Linux-P1 slice after AUR is live and must not block AUR.

**S1 landed:** `build_tools/package_managers/` generates `am-configurator-bin`
PKGBUILD + `.SRCINFO` from release digests; golden tests in
`tests/test_package_managers.py`.

**S2 status (2026-08-08):** Package tree for **0.1.68** generated from the
published `SHA256SUMS.txt` into `dist/package-managers/am-configurator-bin/`
(gitignored). AUR name `am-configurator-bin` is free (RPC resultcount 0).
**Blocked on owner:** no AUR SSH public key accepted from this machine
(`Permission denied (publickey)` to `aur@aur.archlinux.org`); no
`makepkg`/Arch container here for install proof. Owner must register an SSH
key on AUR, create the package repo, and push. S3 stays gated on the package
being queryable.

## Product priority (owner, 2026-08-08)

Owner wording: *the point of this app is to close the Linux gap for these
keyboards; reducing Linux friction is P1.*

Consequence for this plan: **Linux package-manager channels outrank macOS
and Windows channels.** An earlier draft that put Homebrew + winget first
was wrong for this product. macOS/Windows package managers remain valuable
but are P2 unless the owner later reorders them.

## Objective

Publish AM Configurator through package managers so Linux keyboard owners can
install, upgrade, and get desktop/udev integration without hunting GitHub
Release assets — while keeping GitHub Releases as the single canonical binary
source of truth.

Native installers continue to be built by `.github/workflows/release.yml`
exactly as today. Package managers only *point at* those published bytes
(or, for Flatpak/Snap if authorized later, rebuild under the same version
identity with an explicit plan slice — not a silent second product).

## Current baseline (repo evidence)

- Public install path is GitHub Releases only (README + `docs/installing.md`).
- Signed lane (`.github/workflows/release.yml`) publishes five assets per
  `v*` tag via `softprops/action-gh-release@v2`:
  - `AM-Configurator-<ver>-macOS-arm64.dmg` (Developer ID + notarized)
  - `AM-Configurator-<ver>-Windows-x64-Setup.exe` (Azure Trusted Signing)
  - `AM-Configurator-<ver>-Linux-x86_64.AppImage` (unsigned by standing policy)
  - `SHA256SUMS.txt`
  - `release-manifest.json`
- Canonical version is `am_configurator/_version.py` only (decision 2026-07-28).
- Artifact filenames are fixed by `build_tools/release_manifest.expected_artifacts`.
- Python packaging already exists: `pyproject.toml` name `am-configurator`,
  hatchling wheel/sdist, `[project.gui-scripts] am-configurator = …:main`,
  `uv build` in verification. There is **no** PyPI publish path and no claim
  that `pip install` is a supported user install.
- Desktop entry for Linux: `packaging/linux/am-configurator.desktop`.
- No Homebrew cask, winget manifest, Chocolatey package, Scoop manifest,
  Flatpak, Snap, AUR, or nix expression exists in-tree or as documented
  out-of-tree process.

## Non-goals

- Rebuilding installers inside package-manager CI.
- Mac App Store, Microsoft Store, or Snap Store exclusive distribution.
- Changing the signed-release asset set, filenames, or signing policy.
- Waiving device-safety, Gatekeeper, or SmartScreen guidance.
- Making the Python wheel the primary end-user install (native HID + desktop
  runtime make that a second-class path unless explicitly approved).
- ARM64 release assets (still experimental/non-release per 2026-08-02).

## Invariants (must hold after every slice)

1. **One binary source.** Every package-manager package installs the exact
   GitHub Release asset for that version (same URL, same SHA-256 as
   `SHA256SUMS.txt` / `release-manifest.json`). No rebuild, re-sign, or
   re-package of the payload except format adapters that package managers
   themselves require (cask extracts the `.app` from the DMG; winget runs the
   Setup.exe).
2. **One version.** Package manifests report the canonical
   `am_configurator/_version.py` value. Tag is always `v<version>`.
3. **GitHub Releases stay available.** Docs may add package-manager install
   commands as options; they must not remove the Releases download path.
4. **No secret leakage.** Package-manager PR bots and external repos never
   receive signing secrets. They only need public asset URLs and digests.
5. **Install docs list options only** (decision 2026-08-08). README and
   install docs show how to install — download filename or package-manager
   command — without agent-invented trust narratives, “unsigned Linux” gap
   framing, or other inflated caveats. Do not instruct users to disable OS
   security.
6. **Release identity tests remain green.** Extending distribution must not
   break `tests/test_packaging.py` filename/manifest contracts.

## Linux friction map (what “P1” is actually fixing)

Today a Linux user must: find the GitHub Release, pick the AppImage, `chmod +x`,
run it from a random download folder, and — for Neon 80 — discover
`docs/neon-80-linux.md` and install a udev rule via `--print-udev-rule`.
macOS/Windows users get a signed drag-install / Setup.exe path. That asymmetry
is the product gap this plan attacks first.

| Friction | Fix via package manager |
|---|---|
| Discoverability (`pacman`/`yay`, Software, Flathub) | AUR / Flatpak / etc. listing |
| Manual download + executable bit | Package installs AppImage or app to a PATH location |
| Desktop menu / icon | Install `packaging/linux/am-configurator.desktop` + icon |
| Neon 80 HID permissions | Ship or install `60-am-neon-80.rules` (or post-install that runs the documented print path) |
| Upgrades | Package manager update path pinned to new release digests |

## Channel matrix (ordered by product fit under Linux-first)

| Channel | Platform | Payload | Linux-gap value | Effort | Notes |
|---|---|---|---|---|---|
| AUR (`am-configurator-bin`) | Arch + friends | AppImage | High for Arch users | Low | Thin wrap of existing asset; can install desktop file + udev rule |
| Flatpak | Broad Linux | rebuilt or bundled app | High for Ubuntu/Fedora/etc. | High | HID/udev + WebKit sandbox work; best “Software app store” reach |
| nixpkgs | NixOS + nix | derivation | Medium | Med | Community PR; strong for NixOS keyboard people |
| Snap | Broad Linux | snap | Low–med | High | Confined HID often painful; lower priority than Flatpak |
| Homebrew Cask | macOS | signed DMG | None for Linux gap | Low–med | P2 — signed asset ready |
| winget | Windows | signed Setup.exe | None for Linux gap | Low–med | P2 — silent flags needed |
| Scoop / Chocolatey | Windows | Setup.exe | None for Linux gap | Low–med | P3 Windows depth |
| PyPI | all | wheel | Weak as desktop path | Med | Developer path only unless owner elevates it |

Phase order (D1a + D1b recorded):

1. **P1 — AUR first** (AppImage + desktop + udev). **Flatpak next** in the
   same Linux-P1 program, non-blocking on AUR. nixpkgs not in this pass.
2. **P2 — Homebrew Cask + winget** (macOS/Windows convenience; already signed).
3. **P3 — Scoop / Chocolatey** (Windows depth).
4. **P4 — PyPI** only if owner wants a developer install path.
5. **P5 — Snap** deferred unless Flatpak is rejected and store reach is still
   required.

## Architecture

```
tag vX.Y.Z
  → release.yml builds/signs/publishes GitHub Release assets
  → release-manifest.json + SHA256SUMS.txt record digests
  → package-manager update job (or maintainer script) reads digests
  → opens/updates external manifests:
       AUR PKGBUILD | Flatpak (if authorized) | later brew/winget/…
  → Linux users install via yay/paru / flatpak / …
```

In-repo responsibilities:

| Concern | Location |
|---|---|
| Canonical version | `am_configurator/_version.py` |
| Release asset names + digests | `build_tools/release_manifest.py`, published `SHA256SUMS.txt` |
| Generate package-manager stubs from a release | new `build_tools/package_managers/` helpers (pure, deterministic) |
| Tests for stub generation | `tests/test_package_managers.py` |
| Docs install paths | `docs/installing.md`, README download section |
| Automation (optional later) | new workflow job on `release` success or `workflow_dispatch` |

Out-of-repo responsibilities (external PRs / taps):

- AUR package (owner-maintained `am-configurator-bin` preferred)
- Flathub / Flatpak remote (if D1b includes Flatpak)
- nixpkgs (if D1b includes it)
- Later: `Homebrew/homebrew-cask` (or owner tap), `microsoft/winget-pkgs`,
  Scoop, Chocolatey

## Package identity (D2 approved)

| Field | Value |
|---|---|
| Product name | AM Configurator |
| AUR package | `am-configurator-bin` |
| Desktop / command name | `am-configurator` |
| Homepage | `https://github.com/roethlar/AMKB-GUI` |
| License | MIT |
| Flatpak app id (later) | `io.github.roethlar.AMConfigurator` |
| Homebrew cask token (P2) | `am-configurator` |
| winget PackageIdentifier (P2) | `Roethlar.AMConfigurator` (confirm if branding requires otherwise) |
| Scoop / Chocolatey (P3) | `am-configurator` |
| PyPI name | already `am-configurator` |

Installer silent flags (must be proven on a real Setup.exe before winget/Choco):

- Inno Setup default silent: `/VERYSILENT /NORESTART` (and `/SUPPRESSMSGBOXES` if needed).
- Confirm per-user vs machine-wide install path matches what winget expects
  (`InstallerScope: user` vs `machine`) from `packaging/windows/AMConfigurator.iss`.

## Implementation slices

Each slice is one commit after D1b (and any per-slice owner gate). Do not start
a later slice until the prior is verified and committed. Slice order follows
**Linux first**.

### S0 — Record remaining channel decision and package identity

- Product priority already recorded (Linux friction is P1).
- Write Decision D1b (exact Linux channel set for P1) and D2 (identifiers)
  into `.agents/decisions.md`.
- Update this plan status line to “Approved for implementation through P1”.
- Update `.agents/state.md` Next to point at this plan’s active slices.

No product code.

### S1 — Deterministic package-manager stub generator (Linux first)

Files:

- `build_tools/package_managers/__init__.py`
- `build_tools/package_managers/common.py` — load version, expected filenames,
  digests from a local `SHA256SUMS.txt` or `release-manifest.json`
- `build_tools/package_managers/aur.py` — PKGBUILD + `.SRCINFO` for
  `am-configurator-bin` (AppImage)
- Later modules only when their phase is authorized:
  `flatpak.py`, `homebrew_cask.py`, `winget.py`, …
- `tests/test_package_managers.py`

Behavior:

- Input: version, path to digests (or release-manifest), optional asset base URL
  defaulting to
  `https://github.com/roethlar/AMKB-GUI/releases/download/v{version}/`.
- Output: printed or written stub files only (no network, no AUR push).
- AUR package **must** reduce friction, not only re-host the binary:
  - Install AppImage to a stable path (e.g. `/usr/bin/am-configurator` wrapper
    or `/opt/am-configurator/…` — pick one and document it).
  - Install `packaging/linux/am-configurator.desktop` and the app icon.
  - Install the Neon 80 udev rule to `/usr/lib/udev/rules.d/` (or
    `/etc/udev/rules.d/` per AUR norms) from
    `am_configurator/data/60-am-neon-80.rules`, with a `.install` note to
    reload udev and replug the board (mirror `docs/neon-80-linux.md`).
  - `optdepends` / depends only as required for running the AppImage on Arch.

Guards:

- Reject version that is not the three-part canonical pattern.
- Reject missing Linux AppImage digest.
- Snapshot-test generated PKGBUILD/`.SRCINFO` against golden files under
  `tests/fixtures/package_managers/` for a fixed fake version/digest set.

Verification: `uv run --frozen python -m unittest tests.test_package_managers -v`
and red-prove one assertion by temporarily breaking a golden digest.

### S2 — AUR package live (P1 core)

1. Generate PKGBUILD via S1 from a published release’s digests.
2. Build/install on Arch (or Arch container): `makepkg -si`, launch app,
   confirm desktop entry, confirm udev rule file is present, About version
   matches canonical.
3. Publish to AUR under the D2 package name (owner AUR account; agent does not
   hold the SSH key unless the owner provides a deliberate path).
4. Document only after the package is queryable: add the AUR install command
   as one install option in README + `docs/installing.md` (decision 2026-08-08:
   options only, no inflated framing).

### S3 — Docs: add package-manager options after AUR is live

Per decision 2026-08-08 (install docs list options only):

- README and `docs/installing.md`: add the live AUR command
  (`yay -S am-configurator-bin` or equivalent) as an install option alongside
  the existing AppImage / Releases paths. No prominence contest, no trust
  essay, no “unsigned Linux” callout, no demoting Releases.
- `docs/neon-80-linux.md`: if the package already installs the udev rule, say
  that in one plain sentence so users do not double-install it; keep the
  AppImage `--print-udev-rule` path for non-package installs.
- Packet/docs tests pin the real package name only when the docs claim it;
  do not invent channels or narrative claims.

### S4 — Flatpak (P1 if D1b includes it; else separate phase)

Only when D1b authorizes Flatpak. This is **not** a thin AppImage wrap:

- Decide runtime strategy (bundle vs org.freedesktop/Gnome runtime +
  WebKit/HID feasibility) in a short design note inside this plan or a
  linked slice before coding.
- Prove device access: open hidraw/serial for supported boards under Flatpak
  permissions (`--device=all` is a last resort and must be owner-visible).
- Flathub submission and CI build of the Flatpak from the same version tag.
- Docs only after a user can `flatpak install …` successfully.

If Flatpak device access cannot be made reliable without rewriting the
transport layer, stop and report — do not ship a Flatpak that cannot talk to
keyboards.

### S5 — nixpkgs (only if D1b includes it)

- Derivation fetching the AppImage (or building from source if cleaner on Nix).
- Desktop item + udev rule packaging consistent with S2 goals.
- PR to nixpkgs; docs after merge.

### S6 — P2 Homebrew Cask

Generator module + cask PR/tap after Linux P1 exit criteria. Same rules as the
earlier brew path: signed notarized DMG only; docs after live.

Owner pick if needed: owner tap first vs official `homebrew-cask`.

### S7 — P2 winget

- Prove silent install flags against `packaging/windows/AMConfigurator.iss`
  before submission (`/VERYSILENT` family only if real Setup.exe accepts them).
- Generate manifests; PR to `microsoft/winget-pkgs`; docs after live.

### S8 — P3 Scoop / Chocolatey

Windows depth only after P2 or if owner pulls them forward.

### S9 — P4 PyPI (optional developer path)

Trusted Publishing for wheel+sdist only; never primary desktop claim for Linux
gap closure.

### S10 — Snap

Deferred. Prefer Flatpak for broad Linux store reach.

## Release-process integration

After P1 is live, every public release gains two maintainer steps (manual until
automation lands):

1. Wait for `release.yml` publish job green and assets live.
2. Run:

   ```sh
   uv run --frozen python -m build_tools.package_managers \
     --version "$(uv run --frozen python build_tools/release_info.py version)" \
     --sums path/to/SHA256SUMS.txt \
     --out dist/package-managers/
   ```

3. Open/update external PRs with generated stubs.
4. After merge + availability, bump nothing in-app — external packages already
   pin the release version.

Do not block the GitHub Release publish job on package-manager PR merge.
External review latency must not delay the canonical download.

## Verification

Per slice:

- Full entry point from `.agents/repo-guidance.md` when touching packaging
  code, workflows, or install docs that tests pin.
- Focused unittest for generators always.
- Platform-specific: real `brew install --cask`, `winget install --manifest`,
  etc., on maintainer machines before first public claim.
- Never write to a keyboard as part of package-manager verification.

## Risks

| Risk | Mitigation |
|---|---|
| External review rejects identifiers or silent flags | Prove silent install (S2); choose boring identifiers (D2) |
| Homebrew audit fails on quarantine/signing | Already notarized; test `spctl` on cask install |
| winget installer scope mismatch (user vs machine) | Read ISS; set `InstallerScope` to match |
| Docs advertise broken install commands | Docs slice only after package is live; tests pin identifiers |
| Double maintenance of digests | Generate from release-manifest only; never hand-edit sha256 |
| PyPI users expect full GUI without system deps | Docs boundary; optional path only |
| Automation opens bad PRs | Manual first submission; automate only after one success |

## Owner decisions

Present **one at a time in chat**. Record each approved wording in
`.agents/decisions.md` before implementing the dependent slice.

### D1a — Product priority — **recorded 2026-08-08**

Linux friction reduction is P1 for package-manager work; this app’s point is
closing the Linux gap for these keyboards. macOS/Windows package managers are
secondary.

### D1b — Linux channel set for P1 — **recorded 2026-08-08 (option A)**

AUR first as the landed package. Flatpak is the immediate next slice under the
Linux-P1 program and must not block AUR.

### D2 — Package identifiers — **recorded 2026-08-08 (“yes”)**

| Field | Value |
|---|---|
| AUR package | `am-configurator-bin` |
| Desktop / command name | `am-configurator` |
| App display name | `AM Configurator` |
| Homepage | `https://github.com/roethlar/AMKB-GUI` |
| License | MIT |
| Flatpak app id (later) | `io.github.roethlar.AMConfigurator` |

### D3 — macOS/Windows package managers after Linux P1

Confirm P2 = Homebrew + winget (and brew landing place) when Linux P1 exits.

### D4 — PyPI

Yes (developer path) / no for now.

### D5 — Automation timing

Manual AUR/Flathub updates until first success vs early bots.

## Exit criteria (Linux P1 complete)

Depends on D1b. Minimum if D1b = A:

- [ ] D1a + D1b + D2 recorded.
- [ ] AUR generator + tests landed.
- [ ] `am-configurator-bin` (or chosen name) installable via AUR helper.
- [ ] Package installs desktop entry + Neon udev rule (or proven equivalent).
- [ ] README + `docs/installing.md` list the live AUR install option alongside
      existing download options (options only; no inflated narrative).
- [ ] Packet/docs tests green; full verification entry point green.
- [ ] `.agents/state.md` reflects Linux package-manager path as live.

If D1b includes Flatpak: also a keyboard-capable Flatpak install path and
docs, or an explicit recorded stop if device access cannot be made reliable.

## Authority

- Canonical version: decisions 2026-07-28 / current `_version.py`.
- Signed installers: decision 2026-08-07.
- GitHub Releases as public asset host: public-release plans and README.
- This plan does not supersede device-safety or release-identity gates.

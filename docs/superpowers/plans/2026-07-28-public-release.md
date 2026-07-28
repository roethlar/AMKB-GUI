# Public Release

Status: approved by the owner on 2026-07-28, with the unconditional requirement
that every application launch starts on Keymap. The owner also settled two
permanent product constraints: every installer remains unsigned, and the
application has one canonical version everywhere. This plan sets that version
to **0.1.64** and publishes it as the repository's normal public GitHub Release.
Unsigned status is a concise install-time fact, not a beta label, release title,
application banner, or substitute product identity. Plan approval authorizes
implementation and local verification only; push, hardware write, release
publication, and Reddit posting retain their explicit gates.

Implementation status: slices 0–7 and the local pre-publication gates completed
on 2026-07-28. Push and the final GitHub, platform, hardware, publication, and
announcement gates remain pending.

## Objective

Publish one honest, reproducible, publicly downloadable AM Configurator release
for macOS arm64, Windows x64, and Linux x86-64, then prepare a Reddit
announcement that cannot direct users to an old build or overstate hardware,
AI, signing, or firmware support.

The release must:

- contain the completed Neon 80 and unified Lighting Studio work on the final
  `main` commit;
- use canonical version `0.1.64` across source metadata, the UI, local and CI
  builds, filenames, manifest, Git tag, release title, release notes, and
  announcement;
- make the absence of Apple notarization and Windows Authenticode signing
  explicit before download and before first launch;
- retain all existing build, license, provenance, device-safety, and
  verification gates;
- provide SHA-256 hashes and free GitHub OIDC/Sigstore build attestations
  without claiming that either replaces platform code signing;
- prove the exact release artifacts, not merely a local build from a nearby
  commit; and
- leave release publication and any Reddit post behind explicit outward-action
  gates.

## Fixed constraints

- Do not sign or notarize application installers. This is a permanent product
  constraint, not a deferred release task.
- Do not enroll in, purchase, borrow, share, or request access to a paid
  developer or code-signing account.
- Do not create or distribute a self-signed Windows certificate. It does not
  establish a trusted publisher or SmartScreen reputation and would imply more
  assurance than it provides.
- Keep the current deterministic macOS ad-hoc signing step
  (`codesign --sign -`) so bundle integrity and the FFmpeg provenance
  relationship remain verifiable. Never call it Developer ID signing or
  notarization.
- Leave the Windows installer Authenticode-unsigned. Never describe it as
  signed, trusted, or SmartScreen-approved.
- Do not tell users to disable Gatekeeper, SmartScreen, Defender, antivirus, or
  browser protections globally. Document only the per-application operating
  system approval flow.
- Do not add `xattr -dr`, `spctl --master-disable`, Defender exclusions, or
  equivalent security-bypass commands to product code, installers, docs, or
  release copy.
- Do not upload release candidates to third-party malware scanners or mirrors
  without a separate outward-action approval.
- Do not make paid AI credentials or provider spend a release prerequisite.
  Unqualified provider paths remain optional and are described as
  experimental rather than silently treated as proven.
- Do not weaken automated tests, package-content checks, typed write
  confirmation, device identity checks, or hardware unlock behavior because
  the packages are unsigned.
- Do not use “unsigned by design,” all-caps warning copy, a warning banner, a
  beta label, or the GitHub prerelease flag. State the unsigned fact once in
  ordinary download/install language and provide the necessary OS-specific
  first-launch instructions.
- Do not derive application versions from a local build counter, GitHub
  workflow run number, date, commit count, platform, or packaging attempt.
  Those values are diagnostic provenance fields only.

## Current baseline

Re-verify every fact before implementation or publication; these facts describe
the 2026-07-28 planning baseline.

- `main` and `origin/main` point to
  `8b50fb916f8e5c10321734f455f256002051839b`.
- CI run `30369190578` and Desktop installers run `30369190195` passed for that
  commit.
- Desktop workflow run 34 produced temporary `0.1.34` macOS, Windows, and Linux
  artifacts. That number came from the workflow run and is historical build
  evidence, not a product-version floor. The artifacts are not the final
  release candidate because release-preparation changes still have to land.
  They are Actions artifacts, not durable public release assets, and expire on
  2026-08-11.
- The public GitHub Releases page exposes only `v0.1.11`, whose tag points to
  `98abb138406093dacea97df2b49be91aa11fdf10`. It is not a release of the
  current product.
- The source tree says `0.1.0`, Desktop workflow run 34 stamped `0.1.34`, and
  local native acceptance reached `0.1.63`. These are three names for one
  product state and are unacceptable. The existing local counter and
  workflow-run stamping must be removed before another native build. Because
  users and acceptance work had already seen `0.1.63`, the first canonical
  public version must be greater than it; `0.1.64` is the minimum
  non-regressive choice.
- The current desktop workflow also triggers on `v*` tags. A release tag
  therefore triggers a redundant second artifact set. A tag must label an
  already-qualified final candidate, not start another differently identified
  build.
- `README.md` still says “before the first tagged release,” omits Neon 80 from
  the supported-keyboards table, and does not describe the current unified
  Lighting Studio, PNG/BMP import, mixed Library, or exact unsigned-install
  approval flow.
- Neon 80 physical identity, keymap/macro round trips, Esc+F2 unlock, axial and
  head mapping, independent lighting timelines, and a complete lighting write
  passed through native build 60. The final unified-Lighting acceptance used
  local native build 63 without a new hardware write.
- The final unified-Lighting acceptance exercised a deterministic fake recipe
  provider, not a live API credential or request. The macOS machine previously
  had a working local Ollama model, but its current availability must be
  rechecked and the application must never download a model to satisfy this
  plan.
- The native packaging path already verifies the macOS ad-hoc signature,
  mounted DMG smoke, Windows install/launch/uninstall, Linux AppImage launch,
  bundled licenses/notices, pinned FFmpeg source/signature, and package
  allowlists.

## Authority and supersession

- `.agents/decisions.md` owns the no-paid-signing-account constraint and the
  existing product decisions.
- `.agents/repo-guidance.md` owns the current automated verification entry
  point and native-build rule.
- `docs/superpowers/plans/2026-07-24-release-hygiene.md` is complete and remains
  authoritative for attribution, sdist allowlisting, documented verification,
  and the Python 3.11 floor. This plan extends it; it does not reopen those
  choices.
- `docs/superpowers/plans/2026-07-25-am-neon-80-support.md` and
  `docs/neon-80-hardware-verification.md` own Neon behavior and prior physical
  evidence.
- `docs/superpowers/plans/2026-07-27-unified-lighting-studio-library.md` owns
  the shipped Lighting, Library, media, and optional-AI behavior.
- This plan owns public release identity, unsigned-install communication,
  candidate provenance, release-candidate qualification, GitHub publication,
  and announcement readiness.

## Release identity and version invariants

`am_configurator/_version.py` is the sole canonical product-version source. Set
it to `0.1.64`. Configure Hatch to derive Python project metadata from that file
instead of repeating a literal version in `pyproject.toml`.

Every build of the same source version remains `0.1.64`:

- local native builds;
- GitHub pull-request and `main` builds;
- application UI;
- Python package metadata;
- macOS bundle and DMG;
- Windows application and installer;
- Linux AppImage;
- artifact names;
- release manifest and checksums;
- Git tag and GitHub Release; and
- release notes and announcement.

Local build counters and GitHub workflow run numbers are not versions. Keep the
workflow run ID/number and source commit in logs, Actions metadata, attestations,
and `release-manifest.json` so two attempts remain distinguishable without
renaming the product.

The following are hard release invariants:

- The workflow run event is `push`, its branch is `main`, and its conclusion is
  `success`.
- The candidate workflow `headSha`, final local `HEAD`, and remote `main` SHA
  are identical before publication.
- Source, UI, package metadata, and all native artifacts report `0.1.64`.
- The tag is exactly `v0.1.64`.
- The release title is `AM Configurator 0.1.64`.
- GitHub's prerelease flag is false. This becomes the repository's normal
  latest release.
- The required filenames are exactly:
  - `AM-Configurator-0.1.64-macOS-arm64.dmg`
  - `AM-Configurator-0.1.64-Windows-x64-Setup.exe`
  - `AM-Configurator-0.1.64-Linux-x86_64.AppImage`
  - `SHA256SUMS.txt`
  - `release-manifest.json`
- The About dialog reports `0.1.64` on every platform.
- Do not overwrite a published asset, move or recreate a release tag, rewrite
  the release commit, or silently replace a failed candidate. Fixes receive a
  deliberate canonical version bump, new artifacts, and a new release.

Remove the `v*` tag trigger from `.github/workflows/desktop.yml`. A release tag
is a label for the already-qualified final `main` artifact set, not a request
for a second build. Remove all local-counter and workflow-run-number version
stamping. Guard this behavior in `tests/test_packaging.py`.

## Distribution trust model

The release has three distinct assurance layers. Keep their claims separate.

1. **Transport and hosting**: GitHub serves the public repository, Release
   record, and assets over HTTPS.
2. **Artifact integrity and provenance**: `SHA256SUMS.txt`,
   `release-manifest.json`, and GitHub's keyless build attestation bind each
   released byte sequence to the repository workflow and commit.
3. **Platform publisher trust**: unavailable. macOS has only an ad-hoc code
   signature and no notarization ticket; Windows has no Authenticode signature
   or SmartScreen reputation.

GitHub build attestations may use
`actions/attest-build-provenance`, pinned to a reviewed immutable commit from
the official `actions` repository. Tag/major-version references are
insufficient for this new trust-sensitive step. Grant only the documented
job-level `id-token: write`, `attestations: write`, and `contents: read`
permissions. Run attestation only for a `push` to `main`, never an untrusted
pull request.

Release documentation must say that hashes and attestations detect substitution
and establish GitHub-workflow provenance; they do not suppress Gatekeeper or
SmartScreen and do not identify a platform-trusted publisher.

## Implementation slices

Each slice receives its own commit. Do not begin the next slice until the
current slice is verified and committed. New regression tests must be
red-proven by temporarily reverting the implementation, observing the focused
test fail, restoring the implementation, and observing it pass.

### 0. Record the constraint and approve the plan

Files:

- `.agents/decisions.md`
- `.agents/state.md`
- this plan

Record the permanently unsigned-installer and one-version decisions as
owner-approved. Keep implementation/publication blocked until the owner
approves the revised plan. Correct stale state that says `main` has not been
pushed, and point current work to this plan.

Commit:

`docs: make release identity canonical`

### 1. Establish `0.1.64` as the one product version

Files:

- `am_configurator/_version.py`
- `pyproject.toml`
- `uv.lock`
- `build_tools/release_info.py`
- `build.py`
- `.am-configurator-build-number` (remove)
- `.github/workflows/desktop.yml`
- `tests/test_packaging.py`
- `README.md`

Changes:

- Set `am_configurator/_version.py` to `0.1.64` and make it the only canonical
  version source.
- Change `pyproject.toml` from a repeated literal project version to Hatch's
  dynamic version configuration pointing at `am_configurator/_version.py`.
- Refresh `uv.lock` mechanically and prove built wheel/sdist metadata reports
  `0.1.64`.
- Remove `base_version`, `build_version`, and `stamp_build_version` behavior
  from `build_tools/release_info.py`. `project_version` must strictly read and
  validate the canonical three-part numeric version.
- Keep one read-only CLI path that prints the canonical version and can write
  that same value to `$GITHUB_OUTPUT`; it must never mutate source.
- Remove `reserve_local_build_number`, `--build-number`, temporary version
  stamping/restoration, and counter-file updates from `build.py`.
- Remove the tracked `.am-configurator-build-number` file.
- Make local native artifact names use `project_version()` unchanged.
- Replace the Desktop workflow's
  `stamp --build-number ${{ github.run_number }}` step with the read-only
  canonical-version output.
- Remove the `push.tags: ["v*"]` trigger.
- Retain pull-request, `main` push, and manual-dispatch installer builds.
- Increase candidate artifact retention from 14 to 30 days so a candidate does
  not expire during qualification; GitHub Release assets become the durable
  copy after publication.
- Replace README local-build examples that expose `--build-number`.
- Add a packaging regression guard proving:
  - source import, Python package metadata, local build planning, CI build
    planning, installer definitions, and filenames all use `0.1.64`;
  - no local counter or workflow run number can alter a version;
  - `main` pushes still build installers;
  - tags do not trigger a second installer build;
  - the three platform artifact globs remain present.

Focused verification:

```text
uv run --frozen python -m unittest tests.test_packaging.ReleaseInfoTests.test_one_canonical_version_drives_every_build -v
uv run --frozen python -m unittest tests.test_packaging.ReleaseInfoTests.test_release_tags_do_not_rebuild_a_different_version -v
uv build
```

Commit:

`build: use one canonical application version`

### 2. Remove duplicate branding and move version into About

Files:

- `am_configurator/server.py`
- `am_configurator/web/index.html`
- `am_configurator/web/app.js`
- `am_configurator/web/lighting_state.js`
- `am_configurator/web/style.css`
- `tests/test_app.py`
- relevant `tests/web/*.test.js`

Changes:

- Remove the in-content logo, duplicate `AM Configurator` heading, and prominent
  version pill from the application toolbar. The native window title is the
  desktop title; the browser tab title remains the browser title.
- Reflow the toolbar so document state and actions occupy the application
  chrome directly. Do not replace the removed brand block with another card,
  badge, or framed header.
- Add one quiet, text-styled **About** control at the bottom of the left
  navigation. It must not use primary-button styling or compete with Keymap,
  Macros, Lighting, Settings, Devices, or Write.
- Open an accessible About dialog containing:
  - `AM Configurator`;
  - `Version 0.1.64`, sourced from the same canonical server-rendered value as
    the rest of the application;
  - the independent-community/non-affiliation statement;
  - MIT license identification; and
  - the public GitHub repository link.
- Do not put signing warnings, “unsigned by design,” build counters, workflow
  run numbers, commit counts, or a beta label in the About control or dialog.
  Unsigned-install information belongs in download/install documentation.
- Support click/tap activation, keyboard activation, focus placement, focus
  return, explicit close, backdrop close where consistent with existing
  dialogs, and reduced motion.
- At narrow widths, keep About unobtrusive and reachable without creating
  horizontal overflow or a second nested-window visual boundary.
- Change `normalizedRoute` and hash parsing so an absent, empty, or invalid
  route falls back to Keymap, not Lighting.
- Start every new page/application launch on Keymap unconditionally. Ignore a
  previously selected section, persisted route, session route, and startup URL
  hash for initial route selection.
- Preserve active lighting-job identity separately from route selection so
  starting on Keymap does not discard or cancel work.
- Allow normal Keymap, Macros, Lighting Studio, Lighting Library, and Settings
  navigation after startup, including browser history within that running
  session. None of those choices changes the next launch route.
- Replace the initial URL/history entry with Keymap so the visible hash and
  active navigation agree immediately after boot.
- Keep the existing no-document empty state: launch opens the Keymap section
  and explains how to open a configuration.

Regression guards must prove:

- the application shell has no visible duplicate product title;
- no version appears in the normal toolbar/sidebar state;
- About is the only normal UI route that reveals the product version;
- the dialog reports exactly `0.1.64`;
- the About control is semantically interactive but lacks action-button
  classes;
- close/focus behavior is accessible; and
- every fresh boot selects Keymap despite saved Lighting, Library, Macros, or
  Settings state and despite a startup hash, while active-job recovery remains
  intact; and
- wide, narrow, zoomed, and reduced-motion layouts remain overflow-free.

Focused verification:

```text
uv run --frozen python -m unittest tests.test_app.AppShellTests.test_version_lives_only_in_about -v
node --test tests/web/about_dialog.test.js tests/web/navigation_state.test.js
```

Commit:

`fix: move application version into About`

### 3. Generate a strict cross-platform release manifest

Files:

- `build_tools/release_manifest.py`
- `tests/test_packaging.py`
- `.github/workflows/desktop.yml`

Implement one stdlib-only helper that receives:

- semantic application version;
- 40-character lowercase commit SHA;
- numeric GitHub workflow run ID and run number;
- repository slug;
- an input directory containing downloaded candidate artifacts; and
- explicit output paths for `release-manifest.json` and `SHA256SUMS.txt`.

The helper must:

- accept only a three-part numeric version;
- require exactly one regular, non-symlink file for each expected platform
  filename and reject missing, duplicate, renamed, empty, or extra installer
  files;
- reject paths escaping the supplied candidate root;
- stream SHA-256 calculation rather than reading a complete AppImage into
  memory;
- write deterministic UTF-8/LF output atomically;
- sort checksum rows by filename;
- record schema version, app version, source commit, repository, workflow run
  ID/number, platform, architecture, filename, byte size, and SHA-256;
- contain no local absolute path, username, environment dump, credential,
  signed URL, or temporary URL; and
- refuse to replace an existing manifest whose contents differ.

After the matrix installer jobs, add a `candidate-metadata` job that:

- runs only for a push to `main` or an explicit manual dispatch, not for pull
  requests;
- checks out the same commit;
- downloads all three installer artifacts with
  `actions/download-artifact`, pinned to a reviewed immutable commit;
- reads the canonical version with the existing release metadata helper;
- runs `release_manifest.py`;
- uploads the manifest and checksum file as a separate candidate-metadata
  Actions artifact; and
- retains it for 30 days.

Unit tests must cover the happy path, filename/version mismatch, missing
platform, extra installer, empty file, symlink, traversal, malformed version,
malformed SHA, deterministic ordering, path redaction, and conflicting
replacement.

Focused verification:

```text
uv run --frozen python -m unittest tests.test_packaging.ReleaseManifestTests -v
```

Commit:

`build: generate strict release manifests`

### 4. Add free keyless build provenance

Files:

- `.github/workflows/desktop.yml`
- `tests/test_packaging.py`

Changes:

- Keep the installer and metadata jobs read-only.
- Add one downstream provenance job with job-scoped `contents: read`,
  `id-token: write`, and `attestations: write`. It runs only after the installer
  matrix and metadata job succeed.
- Gate the complete provenance job to `github.event_name == 'push'` and
  `github.ref == 'refs/heads/main'`, so pull requests and manual-dispatch builds
  cannot request an OIDC token.
- Download and attest each exact native installer after its platform smoke has
  passed, using the official GitHub provenance action pinned to an immutable
  commit.
- Attest `release-manifest.json` and `SHA256SUMS.txt` together as the fourth
  provenance record.
- Add static workflow guards for the exact event condition, least-privilege
  permissions, immutable action reference, and installer subject path.
- Add release documentation for `gh attestation verify <file> --repo
  roethlar/AMKB-GUI`.

Do not add GPG keys, self-signed platform certificates, repository secrets, or
third-party signing services.

Focused verification:

```text
uv run --frozen python -m unittest tests.test_packaging.ReleaseInfoTests.test_main_installers_receive_keyless_provenance -v
```

Commit:

`build: attest release artifacts`

### 5. Correct public support and download documentation

Files:

- `README.md`
- `docs/installing.md`
- `docs/neon-80-linux.md`
- `tests/test_packaging.py`

README changes:

- Remove “before the first tagged release.”
- Make the GitHub Releases page the only public installer source. Actions
  artifacts are candidates for maintainers, not end-user downloads.
- Add AM Neon 80 to the support table with its `NEON80` identity, 87-key
  physical layout/89 axial LEDs, 46×5 head matrix, derived top-display channel,
  four keymap layers, and 16-macro firmware limit.
- Describe the unified Lighting Studio accurately: manual per-frame painting,
  keyboard-shaped targets, GIF import, PNG/BMP still import, pan/zoom/stretch,
  local animation effects, optional procedural AI, mixed Library, reversible
  removal, and compatibility-gated profile import.
- State that a full write replaces keymaps, macros, and LED data.
- State that Neon firmware does not expose LED read-back. A device read is not
  a lighting backup; users need a portable JSON with known LED data or the
  original media/configuration needed to reconstruct it.
- Link the Linux udev instructions.
- Describe optional AI as off by default. When it is off, no AI controls or
  automatic Ollama discovery appear. API use requires the user's own provider
  key and can send the entered prompt/recipe request to that provider.
- Preserve the independent-community/non-affiliation statement.

`docs/installing.md` must provide:

- exact SHA-256 and GitHub-attestation verification instructions;
- macOS: verify the DMG, drag to Applications, attempt one launch, then use
  System Settings → Privacy & Security → Open Anyway for that application;
- Windows: inspect the hash, open the installer, use SmartScreen's **More
  info** → **Run anyway** only if the displayed filename/hash/repository match;
- Linux: mark the AppImage executable if the browser removed the bit, launch
  it normally, and install the shipped udev rule for Neon access;
- a clear explanation of what ad-hoc, unsigned, and unattested each mean; and
- explicit warnings never to disable OS security globally.

Add static packaging/doc guards for the Neon support row, no stale
first-release text, and the absence of prohibited bypass commands.

Commit:

`docs: explain unsigned installation and Neon support`

### 6. Refresh public screenshots without private state

Files:

- `docs/images/keymap.png`
- `docs/images/led-studio.png`
- optionally one new `docs/images/neon-lighting.png`
- `README.md`

Use deterministic fixture data in the browser/native UI. Screenshots must:

- show one product title supplied by the native/browser chrome, not a second
  in-content title;
- keep the version absent from the normal application shell; if an About
  screenshot is needed for install support, capture it separately rather than
  turning it into the README hero;
- show the real keyboard-shaped keymap and Lighting geometry;
- make multi-LED keys individually identifiable;
- show the unified Lighting Studio and mixed Library rather than the retired
  UI;
- use a representative Neon pattern without exposing a firmware UID, serial,
  local Library path, provider key, account name, prompt history, or owner
  profile; and
- render cleanly at the README's normal width.

Inspect every image at original resolution before committing it. Search image
metadata for local paths or user-identifying fields and strip nonessential
metadata.

Commit:

`docs: refresh public product screenshots`

### 7. Add public release notes and issue intake

Files:

- `docs/releases/2026-07-public-release.md`
- `docs/releases/2026-07-public-release-reddit.md`
- `.github/ISSUE_TEMPLATE/bug-report.yml`
- `.github/ISSUE_TEMPLATE/config.yml`

The release notes must cover changes since `v0.1.11`:

- Neon 80 read/write support and physical verification;
- correct keymap, macro, axial, and top-display behavior;
- unified Lighting Studio;
- GIF/PNG/BMP composition and local effects;
- mixed Library save/import/remove/restore behavior;
- optional AI master switch and supported adapters;
- write confirmation, compatibility gating, and backup behavior;
- supported operating systems and architectures; and
- all known limitations listed below.

Known limitations must include:

- unsigned/not notarized packages and the expected first-launch OS flows;
- independent community project, not endorsed by Angry Miao;
- firmware revisions may differ;
- Neon LED state cannot be read back;
- a confirmed write is a complete-configuration write;
- macOS artifact is arm64 only; Windows and Linux artifacts are x86-64 only;
- other keyboard families retain automated coverage but are not represented as
  freshly physically requalified unless that check actually runs;
- remote AI adapters that lack a live release-candidate smoke are experimental;
  and
- users must keep AM Master, Vial, VIA, QMK Toolbox, and other device-owning
  applications closed during a write.

The issue form must request:

- app version;
- OS/version and architecture;
- keyboard model and firmware identity/version;
- read versus write operation;
- reproducible steps and expected/actual behavior;
- whether another keyboard app was open; and
- sanitized logs/screenshots.

It must tell users not to attach API keys, credentials, private macro text,
complete profiles, firmware UID/serial values, or private Library paths unless
they have deliberately sanitized them.

The Reddit draft must:

- use a normal AM Configurator/Neon feature title with no beta or signing label;
- link directly to the matching normal GitHub Release, not Actions;
- name the tested Neon 80 path without claiming every firmware revision;
- tell users to back up known LED data before a full write;
- include one ordinary body sentence that the installers are not code-signed
  and macOS or Windows may request first-launch approval, then link the detailed
  installation instructions;
- keep AI out of the headline unless every advertised backend receives a live
  qualification;
- invite reports through the issue form; and
- avoid “official,” “safe for every board,” “fully signed,” “LED backup from
  keyboard,” “all AI providers verified,” or equivalent unsupported claims.

Commit:

`docs: draft public release materials`

## Verification gates

All gates are cumulative. A later pass does not excuse an earlier failure.

### A. Clean repository gate

Run the exact current entry point from `.agents/repo-guidance.md`:

```text
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python -m compileall -q am_configurator packaging build_tools
node --test tests/web/*.test.js
node --check am_configurator/web/lighting_state.js
node --check am_configurator/web/lighting_review.js
node --check am_configurator/web/lighting_targets.js
node --check am_configurator/web/lighting_composer.js
node --check am_configurator/web/library_state.js
node --check am_configurator/web/app.js
uv build
```

Also run:

- YAML/action validation with `actionlint` when available;
- the Python 3.11 CI job;
- source and wheel content checks from the completed release-hygiene plan; and
- a tracked/untracked file audit for credentials, `.env` files, machine-local
  paths, captured profiles, firmware UIDs, and oversized binaries.

### B. Local native candidate gate

On macOS arm64:

1. Run `python build.py --skip-sync`.
2. Run the frozen app smoke from the produced bundle and mounted DMG.
3. Run the real WKWebView native-policy smoke.
4. Run `hdiutil verify` against the DMG.
5. Run `codesign --verify --deep --strict` against the mounted app.
6. Inspect signature details and require ad-hoc identity with no Developer ID
   authority or notarization claim.
7. Confirm the About dialog reports the canonical version.

This local build is preflight evidence only. It is not substituted for the
eventual GitHub candidate.

### C. Final GitHub candidate gate

After the approved `main` push:

1. Wait for both CI and Desktop installers workflows to finish.
2. Require every job to conclude `success`; cancelled, skipped-required, or
   neutral is not success.
3. Resolve the Desktop run's `databaseId`, `number`, `headSha`, `headBranch`,
   and `event` with `gh`.
4. Require `event=push`, `headBranch=main`, and `headSha` equal to remote
   `main`.
5. Download the three installer artifacts and candidate metadata into a new
   explicit temporary directory.
6. Run `release_manifest.py` again locally and byte-compare its manifest and
   checksum file with the workflow-generated copies.
7. Verify all four GitHub attestations against `roethlar/AMKB-GUI`.
8. Confirm source metadata, all filenames, and each native artifact report
   exactly `0.1.64`; record workflow run number separately as provenance.
9. Inspect each asset for unexpected files, credentials, local paths, internal
   runtime/model binaries, missing licenses/notices, and missing Linux udev
   data.

Do not create a tag or Release if any comparison fails.

### D. Exact-artifact platform gate

Use the downloaded GitHub candidate bytes.

| Platform | Required evidence |
|---|---|
| macOS arm64 | Browser-downloaded DMG hash matches; `hdiutil verify`; mounted-app ad-hoc signature verifies; normal launch produces the expected Gatekeeper refusal; the documented System Settings **Open Anyway** path launches the app; About reports `0.1.64`; frozen smoke passes. |
| Windows 11 x64 | Download on `netwatch-01`; SHA-256 matches; `Get-AuthenticodeSignature` reports the documented unsigned state; SmartScreen copy is accurate; per-user install, launch, About-version inspection, native-policy smoke, and uninstall pass; Defender is not disabled or bypassed. |
| Linux x86-64 | GitHub runner AppImage smoke passes; SHA-256 and attestation match; AppImage contains license/notices and the udev rule; `--print-udev-rule` emits the shipped rule. Record that no physical Linux Neon check ran unless suitable hardware is actually available. |

A platform warning matching the documented unsigned state is expected. A
quarantine, malware, corruption, launch, install, or runtime failure beyond that
documented flow blocks the release.

### E. Exact-artifact UI and privacy gate

Run the GitHub macOS candidate in a clean temporary application-data and
Library environment:

- first launch is usable at wide and narrow sizes with no console error;
- version is correct;
- AI defaults off and every AI-specific setting/control is absent;
- no Ollama discovery, API call, credential lookup, or Keychain prompt occurs
  while AI is off;
- enabling AI persists intent and exposes setup without falsely reporting a
  backend ready;
- GIF, PNG, and BMP imports render through pan, locked zoom, stretch, preview,
  Apply, and undo;
- each local animation effect works;
- manual per-key/per-frame work can be banked;
- Library save, compatible apply, partial/blocked explanation, remove, Undo,
  restore, and permanent deletion operate only inside the temporary Library;
- permanent deletion requires its existing confirmation and never targets a
  user Library;
- keymap, macro, and Lighting canvases preserve physical key sizing and
  multi-LED labels; and
- reduced-motion and keyboard navigation remain usable.

If the already-installed local Ollama service and a previously selected model
are available, run one real schema-valid setup and generation through the
release candidate without downloading or modifying a model. Record the model
name/digest and result without recording prompt content that is private. If it
is unavailable, keep AI out of the announcement headline and retain the
experimental limitation.

Remote provider live smokes are not required when credentials are unavailable.
If the owner separately authorizes credential use and provider cost, perform
one minimal structured setup/generation request for each advertised provider,
never print or persist the credential outside the OS credential store, and
record only provider, model, date, status, and redacted error category. A
provider not live-smoked remains explicitly experimental.

### F. Exact-artifact Neon hardware gate

This gate requires a fresh hardware-write authorization immediately before the
write. Prior hardware approval does not carry forward.

Preconditions:

- one physically identified AM Neon 80 is connected;
- AM Master, Vial, VIA, QMK Toolbox, and other HID owners are closed;
- the exact GitHub macOS candidate is running;
- a portable JSON known to contain the intended keymap, macros, and LEDs, or
  the source media needed to reconstruct the intended LEDs, is available;
- the temporary Library is selected; and
- the keyboard's current state and restore procedure are understood.

Run:

1. Discover and identify the board as `NEON80`.
2. Read keymap and macros and confirm four layers, macro capacity, and expected
   event counts without treating synthetic black LED placeholders as backup.
3. Confirm the 87-key physical layout, 89 axial LED labels, three separately
   editable spacebar LEDs, and the top-display geometry.
4. Import one GIF and one still image, exercise transform/effect controls, save
   and reopen through Library, and Apply to a nonempty lighting slot.
5. Make one reversible keymap edit and preserve the known macro set.
6. Begin a full write through the normal UI, type `NEON80`, perform the physical
   Esc+F2 unlock, and wait for the complete write and verification.
7. Require exact keymap/macro read-back and a persisted snapshot matching the
   submitted document.
8. Visually confirm the axial and top-display pattern, including asymmetric
   orientation and independent timelines.
9. Restore the owner's desired configuration if the acceptance pattern was
   temporary, using the same guarded full-write path.
10. Record the release version, artifact SHA-256, source profile SHA-256,
    persisted snapshot SHA-256, pass/fail result, and visual confirmation in
    `docs/neon-80-hardware-verification.md` without recording firmware UID or
    private macro contents in public release copy.

Any false success, partial lighting upload, unexpected device identity,
read-back mismatch, loss of a known-restorable configuration, or layout
mislabel blocks publication.

Other keyboard families retain their automated fixture coverage. Do not claim
fresh physical requalification for CyberBoard, Relic 80, or AFA/AFA 2 unless
the corresponding exact-artifact check actually runs. A physical write to any
additional board requires its own fresh authorization.

## Release copy claim boundary

Allowed claims:

- independent, open-source community application;
- normal public release `0.1.64`;
- exact supported operating systems and architectures;
- Neon 80 was physically tested on the recorded firmware identity;
- the listed device families have explicit implementation and automated
  coverage;
- manual configuration works without AI or an account;
- optional AI is hidden/off by default;
- release hashes and GitHub build provenance are available; and
- a confirmed device write is guarded and followed by keymap/macro read-back.

Disallowed claims:

- official, endorsed, or supported by Angry Miao;
- signed, notarized, trusted publisher, SmartScreen-approved, or warning-free;
- safe for every keyboard or firmware revision;
- “backup from keyboard” when LED state cannot be read;
- lighting was verified by read-back;
- all provider APIs are live-qualified when they are not;
- no cloud/network activity after the user explicitly enables and configures a
  remote AI provider;
- zero risk of configuration loss;
- signed, notarized, or warning-free; or
- beta/prerelease merely because the permanent packages are unsigned.

## Pre-publication implementation record

Implementation slices 0–7 landed through `647fac2`. A follow-up repository
privacy audit found one historical device serial in the earlier Neon support
plan; `c774cac` redacts it from the current tree without changing shipped code.
The owner then rejected workflow-derived `0.1.34` as a regression below native
builds that had already displayed `0.1.63`; the completed correction makes
`0.1.64` the first non-regressive canonical release version everywhere.

The local evidence is:

- the cumulative gate passes 683 Python tests on Python 3.13, 81 web tests,
  compile/syntax checks, and source/wheel builds;
- the Python 3.11 floor separately passes all 683 Python tests, compilation,
  and package builds;
- the canonical-version guard was red-proven by temporarily restoring
  `0.1.34`, observing the focused test fail, restoring `0.1.64`, and passing all
  54 focused packaging/release tests;
- the source and wheel report canonical version `0.1.64`;
- a fresh macOS preflight build produced
  `AM-Configurator-0.1.64-macOS-arm64.dmg`, 25,509,941 bytes, with SHA-256
  `6e4c4217ba4bc29aa8fde44d5b91e2bf8c33a50e55d7868fefa0867fd5c167cf`;
- that local DMG passes bundle and mounted-image smoke, the real WKWebView
  policy smoke, `hdiutil verify`, and deep strict ad-hoc signature verification
  with no Developer ID authority;
- the mounted application reports `0.1.64`, while the completed live browser
  acceptance confirms the quiet About dialog reports `0.1.64`, every fresh
  launch opens Keymap, and wide/narrow layouts have no page overflow or console
  error;
- the tracked/untracked audit finds no untracked files, `.env` files, non-test
  credential signatures, firmware UID values, public machine-local paths, or
  oversized tracked files; and
- `actionlint` is not installed locally, so its optional check was unavailable.
  GitHub remains authoritative for workflow execution.

This DMG is local preflight evidence only, not a release asset. No push,
provider request, credential or Keychain access, model mutation/download,
hardware write, release publication, or Reddit post occurred. The next required
action is an explicitly authorized push of `main`; the exact GitHub candidate,
cross-platform acceptance, fresh Neon write authorization and check, release
publication, and announcement review remain pending.

## Publication sequence

Publication is not authorized by plan approval.

1. Finish and commit every implementation slice.
2. Update this plan's completion record and `.agents/state.md` with
   pre-publication evidence.
3. Obtain one explicit push approval, push `main`, and wait for CI plus Desktop
   installers.
4. Complete gates C through F against the final successful `main` run.
5. Confirm the final run still reports canonical version `0.1.64`; its run
   number must not alter source, UI, metadata, or artifact names.
6. Prepare a final release body from
   `docs/releases/2026-07-public-release.md`, substituting only the exact
   commit, run provenance, hashes, attestation instructions, and verified
   limitations. The product version remains `0.1.64`.
7. Present one cold owner gate that names:
   - tag/version and exact commit;
   - all five asset names and hashes;
   - CI, installer, platform, UI, and Neon outcomes;
   - unsigned/notarized state;
   - any AI providers not live-qualified;
   - the exact GitHub Release title/body classification; and
   - the proposed action: create tag `v0.1.64` and the normal public GitHub
     Release `AM Configurator 0.1.64`.
8. On that explicit go, create the release with `gh release create` using
   `v0.1.64`, `--target <exact SHA>`, `--latest`, the approved title/body, and
   exactly the five qualified assets. Do not pass `--prerelease`. Let GitHub
   create the tag at that target; do not perform a separate tag push or trigger
   another installer build.
9. Read back the Release and tag through the GitHub API. Require the tag target,
   normal/latest classification, asset names, sizes, and hashes to match the
   approved set.
10. Test every public asset URL without relying on the maintainer's authenticated
    browser session. Download again and compare SHA-256.
11. Update `.agents/state.md`, this plan's completion record, and any release
    tracker with the actual URL and immutable evidence; commit that bookkeeping.
    Its later push still follows `.agents/push-policy.md`.
12. Replace the placeholder release URL in the Reddit draft and perform a final
    logged-out link/copy review.
13. The owner may post the Reddit copy. An agent may not submit, edit, comment,
    or cross-post it without a separate explicit outward-message authorization.

## Failure and rollback policy

- Before publication, any failed gate rejects the candidate. Fix on `main`,
  commit, obtain the next push approval, and rebuild the same canonical
  `0.1.64` version until one exact candidate passes. Unpublished failed attempts
  do not consume product versions.
- After publication, never overwrite assets or move the tag. A code or package
  fix requires an explicit canonical version bump, new artifacts, and a new
  normal release.
- If a release has a configuration-loss, wrong-device, or false-verification
  defect, stop recommending downloads. Prepare an explicit warning for the
  GitHub Release and Reddit thread and request approval for those outward edits.
- If an installer alone is corrupt, do not silently replace it. Publish a new
  complete three-platform candidate so version identity stays coherent.
- An expected unsigned warning is not a rollback trigger. A warning materially
  different from the documented flow, an antivirus malware classification, or
  inability to launch after the narrow OS approval flow is a blocker to
  announcing that platform.
- If GitHub attestation is unavailable, hashes and all existing gates remain,
  but do not silently omit the promised provenance. Amend this plan and release
  copy before publication.

## Post-release watch

For the first 72 hours after the announcement:

- watch GitHub issues and the Reddit thread for install failures, wrong-device
  reports, configuration loss, false verified-write messages, and firmware
  incompatibility;
- classify reports by app version, platform, keyboard, firmware, and read/write
  path without requesting secrets or unsanitized profiles;
- reproduce locally before changing claims or code;
- put known limitations into the GitHub Release body and a Reddit comment only
  with outward-edit approval;
- treat a reproducible hardware-safety defect as release-critical; and
- choose and commit one new canonical patch version for fixes rather than
  modifying published bytes.

Do not promise future signing. Permanently unsigned installers are a settled
product constraint.

## Completion criteria

The release plan is complete only when:

- the owner has approved the normal `0.1.64` public-release identity and this
  plan;
- every implementation slice is committed and the worktree is clean;
- the full local gate and GitHub CI pass on the final commit;
- canonical version `0.1.64` is identical in source, UI/About, package metadata,
  local/CI planning, all native artifacts, filenames, manifest, tag, Release,
  notes, and announcement;
- one successful `main` Desktop run owns the exact release SHA and provenance
  without becoming a product version;
- the three candidate installers, checksum file, and manifest agree exactly;
- GitHub provenance verifies for every promised subject;
- unsigned first-launch instructions match observed macOS and Windows behavior;
- public docs list Neon and the actual current product;
- the exact candidate passes platform, UI/privacy, and authorized Neon hardware
  acceptance;
- unqualified AI providers are described as experimental and omitted from the
  headline;
- the normal/latest GitHub Release tag, target, assets, notes, hashes, and
  public links are verified;
- the Reddit draft links to that release and stays within the claim boundary;
- release bookkeeping is committed; and
- no paid account, platform certificate, notarization, security bypass, asset
  overwrite, tag move, or unapproved outward message occurred.

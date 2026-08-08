# Repository State

## Now

- **0.1.68 is published** (2026-08-08): tag `v0.1.68` at `cdcf841`, signed
  release run 31240024617 fully green (Release identity, signed Windows
  installer, signed macOS installer, Linux AppImage, Publish), GitHub Release
  "AM Configurator 0.1.68" normal/latest published 04:43Z with all five
  assets. It ships the packaged-TLS-trust fix, and — via the new
  `AM_SMOKE_NET=1` workflow env — every frozen smoke test in that run proved
  the packaged CA trust with a real HTTPS connection. This is the first
  release whose installed builds can reach AI providers over HTTPS on
  ordinary user machines. Owner authorized push, tag, and publication via
  the 2026-08-08 goal directive ("do not stop until there is a signed
  download for all possible platforms on github"); "all possible platforms"
  reads as macOS and Windows signed, Linux unsigned by standing decision
  (no publisher-signing equivalent).
- **Packaged TLS trust is fixed and committed, unpushed** (2026-08-08):
  `028e73b` (fix) and `328a738` (CI guard). Root cause: frozen builds bundle
  an OpenSSL whose default CA path is baked to the build machine
  (`/Library/Frameworks/Python.framework/.../etc/openssl/cert.pem`), so every
  installed build to date — 0.1.66 and the installed 0.1.67 artifact included —
  had zero trusted roots and every HTTPS provider call failed
  `CERTIFICATE_VERIFY_FAILED`, surfaced as the offline "AI service could not
  be reached" error for all API providers. Proven on the installed 0.1.67 via
  `AM_SMOKE_NET=1 --smoke-test` (fails) and on a fresh local build after the
  fix (passes; `certifi/cacert.pem` rides in the bundle). The fix anchors
  `llm.default_tls_context()` to certifi and both workflows now export
  `AM_SMOKE_NET=1` so the packaged-CA reach check gates every frozen smoke.
  **Reviewed clean** (2026-08-08): codereview codex (gpt-5.6-sol @ xhigh,
  standard — codex defaults per owner dispatch) over `6c1d652..328a738`, no
  material issue; record in `.agents/review/outcomes.md`. Release
  consequence: **v0.1.67 was tagged and published at `6c1d652`, before these
  commits** (observed 2026-08-08: `git ls-remote` shows the tag and
  `origin/main` at `6c1d652`; the GitHub Release published 02:42Z), so the
  shipped 0.1.67 still carries the broken TLS trust and AI providers fail in
  it on machines without the build-machine cert path. Shipping the fix needs
  a new owner-gated release (push, version bump, tag); the 0.1.67 release
  notes do not mention the fix (owner-ruled copy — not edited).
- **Separate, environmental:** the owner's Anthropic API account answered
  HTTP 400 "credit balance is too low" (2026-08-08) — Anthropic generation
  needs credits regardless of the TLS fix. Known cosmetic gap, unrecorded as
  work: the app classifies that billing 400 as `bad_response`, whose UI copy
  ("model sent back lighting this app could not use") misleads; reclassifying
  it is unscoped and owner-gated.
- **0.1.67 is published** (2026-08-08): the owner pushed the prepared commits
  and cut `v0.1.67` at `6c1d652`; the GitHub Release "AM Configurator 0.1.67"
  published 2026-08-08T02:42Z, normal/latest. It predates the TLS-trust fix
  above, so its installed builds cannot reach any AI provider over HTTPS on
  machines without the build-machine cert path.
- **The 2026-08-03 copy ruling binds the release-note body, not just the
  announcement.** Its first sentence names release-note copy; the
  no-dialog-mechanics sentence that `4c60d3c` added names announcement copy.
  0.1.67 first shipped a `## First launch` section carrying SmartScreen button
  steps; `267f3ce` removed it and folded the trust facts into Downloads, which
  is how 0.1.64, 0.1.65, and 0.1.66 all did it. The per-OS button-level steps
  stay in `docs/installing.md`, which the notes link, and the 0.1.67 notes test
  now refuses those button phrases in the release body. If the owner reads the
  ruling as announcement-only, the section can come back — nothing else
  depends on its absence.
- **The only functional change since `v0.1.66` is the About panel's Sponsors and
  Ko-fi links** (`am_configurator/web/index.html`). Everything else in
  `v0.1.66..HEAD` was signing/CI, docs, tests, or README images — no keymap,
  macro, lighting, Library, protocol, or AI behaviour moved. The 0.1.67 notes
  say so rather than implying new behaviour.
- **Release-lane assets carry no build attestation, and the docs now say that
  instead of pointing users at it.** `desktop.yml`'s `provenance` job is
  `main`-push-only, so `gh attestation verify` finds nothing for a file built by
  `release.yml`. `docs/installing.md` scopes attestation to candidate builds and
  0.1.67's notes tell users to verify digest plus publisher signature. Adding an
  attest step to `release.yml` remains an open option, not a decision.
- **Visible first-launch trust behaviour on a signed package has never been
  observed.** The 2026-08-03 change-triggered qualification decision names
  signing as a trigger, and signing changed, so the unsigned baseline no longer
  carries. CI asserts signature state, notarization ticket, and Gatekeeper
  primary-signature assessment; nobody has downloaded a signed dmg or installer
  through a browser and opened it. Owner call whether that gates publication.
- **0.1.66 is published** (2026-08-04): GitHub Release
  <https://github.com/roethlar/AMKB-GUI/releases/tag/v0.1.66>, normal/latest,
  tag `v0.1.66` at `f19a806`. All five assets verified by hash, attestation,
  and anonymous download. Local macOS qualification passed.
- The withdrawn `v0.1.65` draft was deleted on 2026-08-04 by owner ruling;
  the `v0.1.65` tag is retained at `ebd0d04` and must not be moved or
  republished.
- The Reddit announcement was stopped by the owner and never posted. The
  Reddit draft has uncommitted working-tree edits; its fate is undecided —
  do not commit it.
- **The signed release lane is PROVEN GREEN on all three platforms** (run
  31228842806, 2026-08-07; `.github/workflows/release.yml`, landed the same
  day): `workflow_dispatch` or a `v*` tag, hard-requiring its signing
  secrets. macOS signs with a Developer ID in a disposable keychain,
  codesigns the dmg itself, notarizes, staples — all verification
  assertions passed. Windows signs the frozen executable and then the Inno
  installer through Azure Trusted Signing — both `Get-AuthenticodeSignature`
  assertions passed. Linux rides along unsigned. Two defects were found and
  fixed by the first exercise (`b1d34fa`): the dmg had no primary signature
  of its own (spctl --type open rejected it; notarization attaches a ticket
  but signs nothing), and `Invoke-TrustedSigning -Files` refuses non-rooted
  paths. One repo-secret correction rode along: `AZURE_SIGNING_ACCOUNT` is
  `roethlar-app-signing` (the Artifact Signing account name; the app
  registration's name 403s). `packaging/macos/build_dmg.sh` takes its
  identity from a non-empty `APPLE_SIGNING_IDENTITY` and otherwise ad-hoc
  signs as before. Bundled Windows DLLs and `.pyd` files stay unsigned;
  only the launched executable and the installer are signed.
- **The signed lane now publishes** (`1f096dc`, pushed; `origin/main` was at
  `c0c489e` on 2026-08-07):
  a `publish` job needs `[macos, windows, linux]`, downloads the three signed
  artifacts into one directory, regenerates `release-manifest.json` and
  `SHA256SUMS.txt` through `build_tools/release_manifest.py`, and makes one
  `softprops/action-gh-release@v2` upload of the five files. It is the only
  job with `contents: write` and runs only on a `v*` tag push — a
  `workflow_dispatch` still stops at the uploaded artifacts, because it has
  no tag to attach assets to. Release title, body, and flags follow the
  hand-published convention: `AM Configurator <version>`, the committed
  `docs/releases/<version>.md` as the body, normal/latest, never draft or
  prerelease, no generated changelog; `release-identity` fails a tag push in
  seconds when that notes file is missing. Nothing about the publish path is
  provable without a real tag run.
- The stale-copy block on the next tag is **cleared**: 0.1.67's notes, README,
  and `docs/installing.md` describe the signatures that exist. `0.1.66.md` keeps
  its own now-false signing sentences as published history and must not be
  edited.
- **Signing conflict RESOLVED by owner override (2026-08-07).** The
  2026-07-28 "permanently platform-unsigned" decision is superseded — see
  `.agents/decisions.md` "2026-08-07 — Installers are platform-signed" for
  the ruling and which of the old clauses survive. The signed lane is now
  legitimate; the README/`docs/installing.md` unsigned copy that entry named as
  outstanding was corrected with 0.1.67 (see the top of Now). Still relevant: the
  2026-07-28 public-release plan removed the `push.tags: ["v*"]` trigger
  from Desktop installers so a tag could not rebuild a candidate;
  `tests/test_packaging.py` still guards that for `desktop.yml`, and the new
  lane reintroduces a tag trigger deliberately, because a signed asset
  cannot come from the unsigned candidate lane.
- The UI redesign is parked until after release and now unblocked to plan:
  element-level, not restyle. Two rejected mockup rounds:
  `/tmp/style-v1..v9*.png`; capture tooling in `/tmp`. Setup rulings (pilot
  screen, prototype form, arrangements per round) still open.

## Next

- **Package-manager distribution (Linux-first):** plan
  `docs/superpowers/plans/2026-08-08-package-manager-distribution.md`. S1
  landed (generator + tests). **S2 prepared for 0.1.68, not published:** tree
  at `dist/package-managers/am-configurator-bin/` (AppImage sha256
  `da72358be994…` matches release); AUR name free. **Blocked:** this machine’s
  SSH key is not authorized on AUR (`Permission denied (publickey)`); no
  makepkg/Arch here. Owner action: AUR account + SSH key → git push package.
  S3 (README install option) only after `am-configurator-bin` is queryable.
- The UI redesign project (rulings needed: pilot screen, prototype form,
  arrangements per round), and the unsupported-board onboarding plan (owner
  approved 2026-08-03): "new keyboard model detected" plus a read-only scan
  packaging a sanitized device report for GitHub submission. Known limit:
  serial-protocol LED geometry is not probeable, so lighting for new serial
  families still needs a physical board or vendor source.

## Blockers

- Whether the published 0.1.67 listing should carry a known-issue note about
  its unreachable AI providers, now that 0.1.68 supersedes it, is the owner's
  call.
- Two things for the owner to rule on before or with that tag: whether the
  unobserved first-launch trust behaviour on a signed package gates publication,
  and whether `release.yml` should attest its assets (the docs currently state
  plainly that it does not).

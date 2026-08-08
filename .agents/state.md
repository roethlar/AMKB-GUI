# Repository State

## Now

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
- **The signed lane now publishes** (`1f096dc`, committed locally, unpushed):
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
- **Blocking the next tag:** `docs/releases/0.1.66.md` is now a release
  *body*, and it states the macOS bundle is not notarized and the Windows
  installer has no Authenticode publisher signature. That copy is false for a
  signed release and must be corrected in the release-notes doc for the
  version being tagged — the same stale-copy work README and
  `docs/installing.md` need.
- Assets published by the tag lane carry no build attestation:
  `desktop.yml`'s `provenance` job is `main`-push-only, so
  `gh attestation verify` covers candidate builds, not signed release assets.
  Unchanged by this slice; decide before the next release whether release
  notes may keep pointing at attestation.
- **Signing conflict RESOLVED by owner override (2026-08-07).** The
  2026-07-28 "permanently platform-unsigned" decision is superseded — see
  `.agents/decisions.md` "2026-08-07 — Installers are platform-signed" for
  the ruling and which of the old clauses survive. The signed lane is now
  legitimate; README/`docs/installing.md` unsigned copy becomes stale with
  the first signed release and updates with it. Still relevant: the
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

- The UI redesign project (rulings needed: pilot screen, prototype form,
  arrangements per round), and the unsupported-board onboarding plan (owner
  approved 2026-08-03): "new keyboard model detected" plus a read-only scan
  packaging a sanitized device report for GitHub submission. Known limit:
  serial-protocol LED geometry is not probeable, so lighting for new serial
  families still needs a physical board or vendor source.

## Blockers

- `0.1.66` publication is complete and the platform-signing conflict is
  resolved (owner override, 2026-08-07 — see Now). Signing itself is proven
  (run 31228842806). Remaining gate: the tag-triggered publish path has never
  run. Proving it needs the local commits pushed and then a real `v*` tag,
  and creating or pushing a tag is explicitly owner-authorized work per
  `.agents/push-policy.md` — it also publishes a real public release, so it
  is not a rehearsal. The stale unsigned release-notes copy must be fixed
  first (see Now).

# Repository State Archive

Superseded entries rotated verbatim from `.agents/state.md`.

## 2026-08-22 drift sweep

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

- **0.1.66 is published** (2026-08-04): GitHub Release
  <https://github.com/roethlar/AMKB-GUI/releases/tag/v0.1.66>, normal/latest,
  tag `v0.1.66` at `f19a806`. All five assets verified by hash, attestation,
  and anonymous download. Local macOS qualification passed.

- The withdrawn `v0.1.65` draft was deleted on 2026-08-04 by owner ruling;
  the `v0.1.65` tag is retained at `ebd0d04` and must not be moved or
  republished.

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

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
- **A signed release lane exists but has never run**
  (`.github/workflows/release.yml`, landed 2026-08-07): `workflow_dispatch` or
  a `v*` tag, hard-requiring its signing secrets. macOS signs with a Developer
  ID in a disposable keychain, notarizes and staples; Windows signs the frozen
  executable and then the Inno installer through Azure Trusted Signing; Linux
  rides along unsigned. `packaging/macos/build_dmg.sh` now takes its identity
  from a non-empty `APPLE_SIGNING_IDENTITY` and otherwise ad-hoc signs as
  before. Nothing about it is proven beyond YAML/shell validity and local
  tests: no run has ever executed, so no signature, notarization, or Trusted
  Signing call has been observed. Bundled Windows DLLs and `.pyd` files stay
  unsigned; only the launched executable and the installer are signed.
- **Conflict awaiting an owner ruling.** The 2026-07-28 decision "Installers
  are permanently platform-unsigned" (`.agents/decisions.md`) says releases
  never depend on or pursue an Apple Developer Program membership or an
  Authenticode certificate, and that the app must never be represented as
  Developer ID-signed. The signed lane above contradicts it, as does the
  presence of `APPLE_*` and `AZURE_*` signing secrets on the GitHub
  repository. Until the owner supersedes or reaffirms that decision, no
  signed artifact may be published and README/`docs/installing.md` unsigned
  copy stays as written. Related: the 2026-07-28 public-release plan removed
  the `push.tags: ["v*"]` trigger from Desktop installers so a tag could not
  rebuild a candidate; `tests/test_packaging.py` still guards that for
  `desktop.yml`, and the new lane reintroduces a tag trigger deliberately,
  because a signed asset cannot come from the unsigned candidate lane.
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

- Publication is complete; owner rulings remain, and one of them now gates
  work: the platform-signing conflict recorded under Now. Signing correctness
  itself is only provable by a real run of the new release workflow, which
  needs a `workflow_dispatch` the owner triggers.

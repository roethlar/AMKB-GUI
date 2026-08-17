# Repository State

## Now

- **v1 is done and locked; all new work is OpenKeeb v2 (2026-08-14):** owner
  ruling, recorded in `.agents/decisions.md`. The v1 default branch is frozen
  (no new feature work or releases; owner-directed fixes only). All new work
  lands on `v2/openkeeb`.

- **Release-lane assets carry no build attestation.** As of `c677b01`,
  `.github/workflows/release.yml` contains no attestation step while
  `.github/workflows/desktop.yml` attests candidate builds; README and install
  guidance accurately distinguish the two lanes. Adding release-lane
  attestation remains an open option, not a decision.

## Next

- **H6 lighting through the hub is approved and in progress (2026-08-17):** H6a
  and H6b are fixture-backed complete. Schema v2, pure capability/transfer
  codecs, and the pinned survey are followed by mutation-refusing Vial/VIA
  read-only snapshots with preserved Vial feature flags, exact current lighting
  state, capability-honest empty results, and ephemeral VialRGB/VIA LED geometry.
  Fake HID proves only definition/protocol-allowlisted GETs occur; no setter,
  save, unlock-start/poll, or hardware mutation was sent. Full verification is
  green at 760 Python and 223 web tests plus compile/syntax/build/diff checks.
  H6c persistent fake-HID writes are next under the continuous H6a–H6e grant in
  `docs/superpowers/plans/2026-08-17-openkeeb-v2-h6-lighting.md`. H6f physical
  keyboard activity, push, release, public identifiers, and spending remain
  separately owner-gated.

- **OpenKeeb v2 implementation follows the approved hub-configurator plan.**
  Its canonical scope, sequence, completed-slice evidence, and write-safety
  boundaries live in
  `docs/superpowers/plans/2026-08-15-openkeeb-v2-hub-configurator.md`. H6
  lighting is next. Public identifiers, releases, money, and future hardware
  writes remain owner-gated.

- **Text banner authoring remains in v2 scope for NEON and Cyberboard.** The
  durable boundary, including its text effects, lives in `.agents/decisions.md`
  under "2026-08-14 — Text banner authoring is in v2 scope"; it needs its own
  approved plan before implementation.

- **The next release notes must carry the retired AI-vault cleanup steps or
  point to README's upgrade section.** No later release record yet owns the
  obligation; `am_configurator/_version.py` is the canonical current version.

- **The generic lighting job/progress scaffold remains an owner choice:** it
  can be removed as dead production code or reused by future deterministic
  tooling. The original finding and bounds live in
  `docs/superpowers/plans/2026-08-14-ai-removal.md`.

- **Whether OpenKeeb v2 exposes a plugin/external-provider surface remains an
  owner question.** It is not required by the approved hub-configurator lane.

- **Package-manager publication is paused.** Canonical status and identifier
  gates live in
  `docs/superpowers/plans/2026-08-08-package-manager-distribution.md`.

## Blockers

- Whether the published 0.1.67 listing should carry a known-issue note about
  its unreachable AI providers, now that 0.1.68 supersedes it, is the owner's
  call. The live GitHub Release body still carries no such note as verified
  2026-08-17.
- Whether unobserved first-launch trust behaviour on a signed package gates a
  future publication remains an owner ruling; automated signature,
  notarization-ticket, and Gatekeeper primary-signature checks do not settle
  the visible launch path.
- Whether `.github/workflows/release.yml` should attest its assets remains an
  owner ruling; as of `c677b01`, it does not, and the docs say so.
- The stopped Reddit announcement was never posted. Its fate remains an owner
  decision; do not post it.

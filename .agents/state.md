# Repository State

## Now

- **v1 is done and locked; all new work is OpenKeeb v2 (2026-08-14):** owner
  ruling, recorded in `.agents/decisions.md`. The v1 default branch is frozen
  (no new feature work or releases; owner-directed fixes only). All new work
  lands on `v2/openkeeb`.

- **Release-lane assets carry no build attestation.** As of `2a80cf0`,
  `.github/workflows/release.yml` contains no attestation step while
  `.github/workflows/desktop.yml` attests candidate builds; README and install
  guidance accurately distinguish the two lanes. Adding release-lane
  attestation remains an open option, not a decision.

- **The UI redesign is parked and unblocked to plan:** element-level, not a
  restyle. Two mockup rounds were rejected, so a new round starts from scratch.
  Setup rulings (pilot screen, prototype form, arrangements per round) remain
  open.

## Next

- **OpenKeeb v2 implementation is active under the approved hub-configurator
  plan:** H0 and H1 are complete; H2 (the Vial spoke) is next. H7 is the queued
  branding overhaul, which the owner ruled is a repositioning rather than a
  rename. The canonical scope and sequence live in
  `docs/superpowers/plans/2026-08-15-openkeeb-v2-hub-configurator.md`. Codec
  work can proceed on fixtures, but live proof awaits a pilot-hardware choice.
  Public identifiers, releases, money, and hardware writes remain owner-gated.

- **Text banner authoring remains in v2 scope for NEON and Cyberboard.** The
  durable boundary, including its text effects, lives in `.agents/decisions.md`
  under "2026-08-14 — Text banner authoring is in v2 scope"; it needs its own
  approved plan before implementation.

- **The next release notes must carry the retired AI-vault cleanup steps or
  point to README's upgrade section.** The product version remains `0.1.68` as
  of `2a80cf0`, so no later release record yet owns that obligation.

- **The generic lighting job/progress scaffold remains an owner choice:** it
  can be removed as dead production code or reused by future deterministic
  tooling. The original finding and bounds live in
  `docs/superpowers/plans/2026-08-14-ai-removal.md`.

- **Whether OpenKeeb v2 exposes a plugin/external-provider surface remains an
  owner question.** It is not required by the approved hub-configurator lane.

- **Package-manager publication is paused:** AUR remains parked by the Arch
  lock; Flatpak preparation exists but must not publish under
  `io.github.roethlar.AMConfigurator`. Retarget both only after OpenKeeb public
  identifiers are approved. Canonical plan:
  `docs/superpowers/plans/2026-08-08-package-manager-distribution.md`.

## Blockers

- Whether the published 0.1.67 listing should carry a known-issue note about
  its unreachable AI providers, now that 0.1.68 supersedes it, is the owner's
  call. The live GitHub Release body still carries no such note as verified
  2026-08-16.
- Whether unobserved first-launch trust behaviour on a signed package gates a
  future publication remains an owner ruling; automated signature,
  notarization-ticket, and Gatekeeper primary-signature checks do not settle
  the visible launch path.
- Whether `.github/workflows/release.yml` should attest its assets remains an
  owner ruling; as of `2a80cf0`, it does not, and the docs say so.
- The stopped Reddit announcement was never posted. Its fate remains an owner
  decision; do not post it.

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
  through H6d are fixture-backed complete. H6d adds capability-gated Vial/VIA
  Lighting Studio controls, current-target per-key geometry, exact-identity
  animation authoring, shared document undo/redo, lighting-only schema-v2
  documents, and persistent-write evidence/counts without adding a hardware
  mutation route. Its bite proof fails when the old keymap requirement is
  restored and passes with the fix. Chrome rendered the supported editor,
  persistent preflight, possibly-accepted write/read-verify recovery, and
  unsupported-capability state at 1000×680, 1280×800, and 1600×1000 with no
  page-level horizontal overflow or console warnings/errors; the isolated fake
  server recorded 6 reads, 4 preflights, and 2 confirmed write attempts. Final
  verification is green at 768 Python and 234 web tests plus
  compile/syntax/build/diff checks. Next action: implement H6e's separately
  started volatile VialRGB stream and rendered start/stop UX. H6f physical
  keyboard activity, push, release, public identifiers, and spending remain
  separately owner-gated.

- **OpenKeeb v2 implementation follows the approved hub-configurator plan.**
  Its canonical scope, sequence, completed-slice evidence, and write-safety
  boundaries live in
  `docs/superpowers/plans/2026-08-15-openkeeb-v2-hub-configurator.md`. H6
  lighting remains in progress. Public identifiers, releases, money, and future
  hardware writes remain owner-gated.

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

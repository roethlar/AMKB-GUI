# Repository State

## Now

- **v1 is done and locked; all new work is OpenKeeb v2 (2026-08-14):** owner
  ruling, recorded in `.agents/decisions.md`. The v1 default branch is frozen
  (no new feature work or releases; owner-directed fixes only). All new work
  lands on `v2/openkeeb`.

- **The v1 Windows line-ending fix is ported to v2 (2026-09-30).** v1's
  `02194cf` (owner-directed on `main`, 2026-09-29) added `.gitattributes`
  pinning `*.desktop`, `*.rules`, `*.sh`, and `packaging/linux/AppRun` to LF,
  because a CRLF Windows checkout changed the bytes the AUR generator hashes
  and failed two `AurGeneratorTests` goldens on every Windows CI run.
  `v2/openkeeb` branched before it and carried the same defect; the
  cherry-pick brings the same file and the same `tests/test_packaging.py`
  guard change. `ci.yml` runs on pushes to `main` and on pull requests only,
  so v2 is exercised on Windows only through a PR.

- **Release-lane assets carry no build attestation.** As of `c677b01`,
  `.github/workflows/release.yml` contains no attestation step while
  `.github/workflows/desktop.yml` attests candidate builds; README and install
  guidance accurately distinguish the two lanes. Adding release-lane
  attestation remains an open option, not a decision.

## Next

- **H6 lighting through the hub is fixture-backed complete through H6e
  (2026-08-17):** H6e adds a bounded, separately confirmed, volatile VialRGB
  preview worker with endpoint/capability reproof, nine-pixel/rate-limited
  scheduling, no backlog or setter retry, persistent-Write exclusion, and one
  restoration attempt on stop, error, shutdown, or 30-second expiry. Fake-HID
  transport/API tests prove no SAVE and restoration accounting. Chrome rendered
  10-pixel preflight, running, explicit-stop, and automatic-expiry/restored
  states at 1000×680, 1280×800, and 1600×1000 with no page overflow, viewport
  escape, or console warnings/errors; persistent Write/Open/Transfer/Keyboards
  actions stayed disabled while running. The unchanged-chunk bite proof failed
  with six reports instead of three when suppression was removed, then passed
  restored. Final verification is green at 778 Python and 238 web tests,
  compilation, every JavaScript syntax check, package build, `git diff --check`,
  macOS frozen build/native tree audit, `--smoke-test`, and
  `--native-policy-smoke`. No physical keyboard was accessed. Canonical slice
  evidence is in
  `docs/superpowers/plans/2026-08-17-openkeeb-v2-h6-lighting.md`; H6f physical
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
  under "2026-08-14 — Text banner authoring is in v2 scope". Its plan is
  drafted, not approved (2026-09-30):
  `docs/superpowers/plans/2026-09-30-openkeeb-v2-panel-text-banners.md`.
  It awaits owner decisions D1 (Cyberboard rendering path) and D2 (plan
  approval); no implementation before D2.

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

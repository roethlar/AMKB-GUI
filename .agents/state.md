# Repository State

## Now

- **0.1.68 is the latest published release** (re-verified as `4cf4d13` on
  2026-08-22): tag `v0.1.68` is at `cdcf841`; GitHub reports “AM
  Configurator 0.1.68” as the normal, latest, non-draft release, published
  2026-08-08T04:43:51Z. It is the first release whose installed builds carry
  usable packaged CA trust for AI-provider HTTPS. The fix is `028e73b`, its
  frozen-network guard is `328a738`, and the clean review is recorded in
  `.agents/review/outcomes.md`.
- **Separate, environmental:** the owner’s Anthropic account answered HTTP 400
  “credit balance is too low” on 2026-08-08. That account needs credits
  independently of the TLS fix. The app still classifies that billing response
  as `bad_response` and shows misleading generic model-output copy; changing
  that behavior remains unscoped and owner-gated.
- **Signed release assets carry no GitHub build attestation** (repo evidence
  re-verified as `4cf4d13` on 2026-08-22): `release.yml` signs and publishes
  them but has no attestation step. Candidate assets from `desktop.yml` are
  different files and remain attested. README, `docs/installing.md`, and the
  0.1.68 notes state this distinction.
- **Visible first-launch trust behavior for a signed package has not been
  observed.** CI proves signature state, notarization ticket, and Gatekeeper
  primary-signature assessment, but no recorded qualification downloaded the
  signed DMG or installer through a browser and opened it.

## Next

- **Package-manager distribution (Linux-first):** the Flatpak
  `io.github.roethlar.AMConfigurator` now has a repeatable one-shot
  prepare/build/install/smoke path. A live Linux Flatpak smoke passed again on
  `gabrielle` as `4cf4d13` on 2026-08-22; machine-specific evidence lives in
  `.agents/machines.md`. No Flathub listing exists yet, so README and install
  docs must not advertise a public Flatpak command. AUR remains blocked below.
  Plan: `docs/superpowers/plans/2026-08-08-package-manager-distribution.md`.
- **UI redesign is unblocked but not specified.** It remains an element-level
  redesign, not a restyle. Owner rulings on the pilot screen, prototype form,
  and review-round arrangement are still open.

## Blockers

- **AUR publication is blocked on owner SSH authorization, not an AUR
  maintenance lock** (re-verified as `4cf4d13` on 2026-08-22):
  `ssh -T aur@aur.archlinux.org` now reaches AUR but returns
  `Permission denied (publickey)`, and
  `https://aur.archlinux.org/packages/am-configurator-bin` returns 404. The
  owner must associate an available public key with the AUR account before the
  prepared package can be published.
- Whether the superseded 0.1.67 GitHub listing should carry a known-issue note
  about its unusable packaged TLS trust remains an owner call.
- The old “before tag” basis for first-launch observation and release-asset
  attestation is falsified: 0.1.68 was published without either. The owner must
  decide whether either becomes a requirement for a future release; current
  docs accurately state that signed release assets have no attestation.

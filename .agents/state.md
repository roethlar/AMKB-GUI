# Repository State

## Now

- **AI removal decided and scoped (2026-08-14):** AI generation leaves the core
  app; the core consumes pixel art and recipes only. Decision:
  `.agents/decisions.md` (2026-08-14). Blast-radius scope:
  `docs/superpowers/plans/2026-08-14-ai-removal-scope.md` — deterministic
  engine (`procedural.py`, recipe schema, library) stays; LLM/provider modules,
  `/api/ai/*` routes, and AI UI go. Sliced removal plan drafted:
  `docs/superpowers/plans/2026-08-14-ai-removal.md` — awaiting owner approval;
  no removal code change is authorized yet. Open questions (owner): which
  branch the removal lands on (v1 default vs `v2/openkeeb`), and whether a
  plugin/external-provider surface lands in OpenKeeb v2.

- **OpenKeeb v2 direction approved (planning only, 2026-08-08):** OpenKeeb is
  the public name for an in-place `2.0.0` successor to AM Configurator. Keep
  the repository/release lineage, publisher signing, Windows installer
  `AppId`, and macOS bundle identifier; do not create a side-by-side product.
  Support is capability-based: keymap, macros, persistent static RGB,
  firmware-defined lighting effects, and custom animation upload are advertised
  and qualified independently. A board can have RGB support without animation
  upload. OpenKeeb is a firmware/configuration manager, not a resident lighting
  host; OpenRGB is finite-session last resort only, never a required background
  service. Initial v2 includes both direct integrations with firmware already
  installed on target boards and a companion-firmware lane needed for broad
  ecosystem coverage. The companion's source/binary/protocol delivery boundary
  remains undecided, and automated firmware flashing is not authorized. Public
  claims remain capability- and hardware-qualified until broader evidence exists.
  The planning record is current as of `ec152c1` (2026-08-09), which corrects
  and supersedes the inverted companion-firmware ruling in `79a3d5e` without
  rewriting history.
  Existing 0.x releases remain unchanged. Development branch `v2/openkeeb`
  was created at planning commit `59f0bb1`; no source rename, identifier
  migration, implementation, or release has been authorized or performed.
  Plan: `docs/superpowers/plans/2026-08-08-openkeeb-v2.md`.

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
  it on machines without the build-machine cert path. The 0.1.67 release notes
  do not mention the fix (owner-ruled copy — not edited); 0.1.68 shipped it
  instead.
- **Separate, environmental:** the owner's Anthropic API account answered
  HTTP 400 "credit balance is too low" (2026-08-08) — Anthropic generation
  needs credits regardless of the TLS fix. Known cosmetic gap, unrecorded as
  work: the app classifies that billing 400 as `bad_response`, whose UI copy
  ("model sent back lighting this app could not use") misleads; reclassifying
  it is unscoped and owner-gated.
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
- The Reddit announcement was stopped by the owner and never posted; its fate
  is undecided — do not post it. The previously recorded uncommitted
  working-tree edits no longer exist: the 0.1.66 draft's last change landed in
  `fcea4eb` (2026-08-05) and the working tree is clean with no stashes as of
  `f3652df`.
- The UI redesign is parked until after release and now unblocked to plan:
  element-level, not restyle. Two mockup rounds were rejected; their `/tmp`
  PNGs and capture tooling no longer exist (verified absent on `nagatha`
  2026-08-14), so a new round starts from scratch. Setup rulings (pilot
  screen, prototype form, arrangements per round) still open.

## Next

- **Lighting-creation direction settled (2026-08-14):** the reopened question
  closed the same day. See `.agents/decisions.md` "2026-08-14 — AI generation
  leaves the core; the core consumes pixel art": AI recipe generation and all
  provider backends come out of the core; creation paths are import, manual
  painting, and a deterministic effect engine with a user-facing picker (to be
  planned); external generation stays outside the boundary, with a possible
  OpenKeeb v2 plugin surface recorded as an open question in the v2 plan. The
  decision authorizes the record and a removal scope only — the removal itself
  needs its own approved plan. An owner-supplied Cyberboard export from the
  community builder was verified to contain finished per-frame `frame_RGB`
  data, not a recipe; that fact grounded the boundary. Next action: draft the
  AI-removal plan from the recorded blast-radius scope, then the picker plan.

- **Procedural effect expansion plan drafted, rulings pending (2026-08-13):**
  assessment of <https://am-led.nanakumi.net> (community AM LED JSON builder;
  unlicensed, no public source — clean-room only) produced
  `docs/superpowers/plans/2026-08-13-am-led-effect-techniques.md`. It adopts
  two techniques (new raster-domain effect kinds; reactive panel→key track
  derivation for CB/NEON) and rejects per-key geometry sampling, LCM frame
  counts, hash-noise-as-change, and word_page text authoring. Ruling 1
  landed 2026-08-13: seven kinds (breathe, chase, ripple, matrix_rain,
  heartbeat, fire, twinkle), strobe excluded. Rulings outstanding, in
  order: reactive mode + switch location, remaining rejection confirmations. No
  implementation authorized.
  Ruling 2 landed 2026-08-14: **text banner authoring is in v2 scope**,
  reversing the plan's `word_page` rejection. NEON and Cyberboard only — the
  billboard panel is the reason the feature exists — and panel display becomes a
  persistent-lighting subcapability. Text authoring needs its own plan before
  implementation. See `.agents/decisions.md` "2026-08-14 — Text banner authoring
  is in v2 scope".
  Strobe is **not declined**; the 2026-08-13 record was wrong twice over. Its
  written rationale (an adjacent-frame-difference conflict) is contradicted by
  the code — `validate_quality` requires adjacent difference greater than zero
  and a strobe maximizes it. And strobe is not a per-key kind at all: on the
  reference builder it is a *text effect* toggle beside Pulse, Flicker, and
  Glow. It belongs to the text banner feature above and arrives with it.
  Ruling 1 stands unchanged at seven per-key kinds.
  **Verification pass 2026-08-14 (`2a3391e`, then this commit): the plan was
  drafted against premises the code contradicts.** Three corrections, each
  marked and dated inline:
  1. **Effect kinds are reachable only by an LLM.** `procedural._KINDS` is
     `{comet, wave, pulse, sparkle, orbit, sweep, noise}`, fed to providers
     through `recipe_schema()`; no effect picker exists in the browser UI.
     Adopting seven more kinds widens what a model may emit and gives users
     nothing. The reference builder is the inverse — 14 user-picked patterns,
     no model. **Delivering its options to users needs a user-facing effect
     picker that does not exist and is unscoped.**
  2. **Ruling 2 is withdrawn, not pending.** It proposed a mode on existing
     panel→key mirroring; there is none. Panel and keys are independent
     surfaces (separate UI targets, separate hardware controls), procedural
     generation refuses to render both at once (`device_mapping.py:1302`),
     and the imported-media path resamples a shared source per track rather
     than deriving keys from panel output. Panel-coupled keys would be new
     feature work.
  3. `FamilySpec` does not hold lighting geometry (`_LAYOUTS` does); the
     OpenKeeb v2 architecture note was corrected to match.
  Ruling 3 (rejection confirmations) remains outstanding. Scope of the pass:
  the effect-techniques plan claim by claim, plus a spot-check of the OpenKeeb
  v2 architecture section. Other docs were not audited.
- **OpenKeeb v2 planning:** capability-based support, firmware-resident lighting,
  and the companion-firmware lane in initial v2 are settled. Next decide whether
  OpenKeeb maintains companion source integrations, complete firmware binaries,
  or only a public protocol; then choose exact pilot boards and public technical
  identifiers one owner decision at a time. No implementation until the durable
  plan is approved.
- **Package-manager distribution paused before publication:** AUR remains
  parked by the Arch lock; Flatpak prepare/build tooling exists but must not be
  published under `io.github.roethlar.AMConfigurator`. Retarget both only after
  OpenKeeb identifiers are approved. Plan:
  `docs/superpowers/plans/2026-08-08-package-manager-distribution.md`.

## Blockers

- Whether the published 0.1.67 listing should carry a known-issue note about
  its unreachable AI providers, now that 0.1.68 supersedes it, is the owner's
  call.
- Two things for the owner to rule on before or with the next tag: whether the
  unobserved first-launch trust behaviour on a signed package gates publication,
  and whether `release.yml` should attest its assets (the docs currently state
  plainly that it does not). Both were open when `v0.1.68` was cut and neither
  was ruled on, so `0.1.68` shipped without them; no entry in
  `.agents/decisions.md` settles either.

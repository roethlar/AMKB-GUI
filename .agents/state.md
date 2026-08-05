# Repository State

## Now

- **Freeze reversed (owner, 2026-08-04): the redesign comes after the
  release.** 0.1.66 proceeds to qualification and the publication gates.
- Landed for 0.1.66: macro editor rework (reviewed in app), synthetic
  screenshots `9e714de`, version bump `777da50`, JPEG import `aa1c263`,
  experimental ARM64 CI `0558685` (first run green on both targets, run
  30884280304), release packet `3345c2c` + tone fixes. Suite fully green as
  of `b88d4b7`.
- The Reddit draft has uncommitted working-tree edits (first-app rewrite);
  the owner stopped Reddit work outright ("LLMs are bad at writing
  human-facing language") — its fate is undecided; do not commit it.
- The UI redesign is parked until after release: element-level, not restyle.
  Two rejected mockup rounds: `/tmp/style-v1..v5*.png` (colorways),
  `/tmp/style-v6..v9*.png` (structural reskins). Capture tooling in `/tmp`
  (`am_capture.py`, `am_make_demo_config.py`, `am_style_variants{,2}.py`,
  `am-demo-config.json`). Setup rulings (pilot screen, prototype form,
  arrangements per round) still open.
- Pushes are paused by owner order; bookkeeping commits stay local. CI
  candidates for qualification need origin, so R66-4's CI half waits on push
  resumption.

## Next

- R66-4 qualification: local macOS build + frozen smoke first; then, once
  pushes resume, CI candidates on the final commit with hash and attestation
  verification. Then the R66-5 gates, each an explicit owner go: tag
  `v0.1.66`, publish the Release, dispose of the `v0.1.65` draft.
- After `0.1.66`: draft a plan for unsupported-board onboarding (owner
  approved 2026-08-03): "new keyboard model detected" plus a read-only scan
  that packages a sanitized device report (product ID, protocol responses,
  keymap/macro capacities) for GitHub submission, so support can be added
  without buying every board. Known limit: serial-protocol LED geometry is
  not probeable, so lighting for new serial families still needs a physical
  board or vendor source; keymap/macro support may ship from a scan alone.

## Blockers

- Pushes paused by owner order; the CI-candidate half of R66-4 waits on
  resumption. No external blocker.

# Repository State

## Now

- **The 0.1.66 release is frozen (owner, 2026-08-04): an element-level UI
  redesign blocks publication.** R66-4 qualification and R66-5 gates do not
  proceed until the redesign ships. The packet (release notes, plan) is
  superseded in UI terms — it describes the current look.
- Landed for 0.1.66 before the freeze: macro editor rework (reviewed in
  app), synthetic screenshots `9e714de`, version bump `777da50`, JPEG import
  `aa1c263`, experimental ARM64 CI `0558685` (first run green on both
  targets, run 30884280304), release packet `3345c2c` + tone fixes. Suite
  fully green as of `b88d4b7`.
- The Reddit draft has uncommitted working-tree edits (first-app rewrite);
  the owner stopped Reddit work outright ("LLMs are bad at writing
  human-facing language") — its fate is undecided; do not commit it.
- UI redesign is the active project. Two mockup rounds were rejected as
  "same elements, restyled": `/tmp/style-v1..v5*.png` (colorways),
  `/tmp/style-v6..v9*.png` (structural reskins). Capture scripts:
  `/tmp/am_capture.py`, `/tmp/am_make_demo_config.py`,
  `/tmp/am_style_variants{,2}.py`; synthetic profile
  `/tmp/am-demo-config.json` (NEON80, layout evidence attached).
- Pushes are paused by owner order; bookkeeping commits stay local.

## Next

- Owner rules on the redesign setup: (1) pilot screen — Lighting workspace
  or whole shell; (2) prototype form — throwaway HTML with new DOM or
  straight into `app.js`; (3) arrangements per round — 2 or 3. Then the
  first element-level prototype round.
- After `0.1.66`: draft a plan for unsupported-board onboarding (owner
  approved 2026-08-03): "new keyboard model detected" plus a read-only scan
  that packages a sanitized device report (product ID, protocol responses,
  keymap/macro capacities) for GitHub submission, so support can be added
  without buying every board. Known limit: serial-protocol LED geometry is
  not probeable, so lighting for new serial families still needs a physical
  board or vendor source; keymap/macro support may ship from a scan alone.

## Blockers

- Release is frozen on the element-level UI redesign (owner, 2026-08-04).
  Origin pushes stay paused. No external blocker.

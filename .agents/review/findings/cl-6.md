# cl-6: CyberBoard display target separation lacks a regression guard

**Severity**: LOW — current behavior is correct, but broadening the new physical-layout selection can silently replace the 200-pixel top display with the 83-LED switch layout while the existing suite stays green.
**Status**: In progress
**Branch**: —
**Commit**: pending

## Evidence
At reviewed head `c01357e90e38b71c9af0303522c104226a68888b`,
`am_configurator/web/app.js:556` gives CyberBoard both the 200-cell
`displayMap` and the 83-cell `physicalLayout`. The target gate at
`am_configurator/web/app.js:3183-3195` is therefore what keeps `frames` on the
40-column display raster while `keyframes` uses physical switch geometry.

The CyberBoard guard at `tests/web/lighting_shell.test.js:500` proves both maps'
shapes but, at the reviewed head, did not pin the target gate that selects
between them. The broader Neon source assertion at
`tests/web/lighting_shell.test.js:577` still matched when that gate was removed.

## Predicted observable failure
If `physicalLayout` is simplified to prefer `model.physicalLayout` regardless
of target, CyberBoard's `frames` editor renders 83 key-shaped controls instead
of the rectangular 40×5 display. The remaining 117 display pixels are
unreachable, while the prior 127-test web suite remains green.

## What
The geometry repair introduced the first model that owns both a display raster
and a physical switch layout, but its test did not guard their target-specific
selection.

## Approach
Extend the existing CyberBoard geometry test to pin both sides of the
separation: `frames` retains 40 columns, and only `keyframes` selects the model's
physical layout before the separate Neon axial projection arm. This keeps the
new invariant beside the geometry assertions it protects.

## Files changed
- `tests/web/lighting_shell.test.js` — guard the CyberBoard display/switch
  target split.
- `.agents/review/findings/cl-6.md` — finding and proof record.
- `.agents/review/index.md` — review-loop status.
- `.agents/review/outcomes.md` — whole-change review outcome.
- `.agents/state.md` — active review-loop pointer.

## Guard proof
`tests/web/lighting_shell.test.js::CyberBoard switch lighting shares the
photographed Keymap geometry` passes with the target gate intact. Temporarily
replacing the gate with unconditional `model.physicalLayout` preference made
that exact test fail (29 pass, 1 fail); restoring the gate returned it to 30
pass, 0 fail.

The full repository gate then passed: 646 Python tests with 5 expected skips,
127 web tests, Python compile checks, all JavaScript syntax checks, and the
`0.1.65` source distribution and wheel build.

## Coder dispute (if any)

## Known gaps
The admitted fix has not yet received its separately owner-gated per-finding
Claude verification verdict.

## Reviewer comments
Raised by: Reviewer: claude / claude-opus-5 / high / standard (inline,
session-only; job `fable-review`) — generation pass over
`6a06f3beb93cb1887b85ed7f0da1171d12ad8c31..c01357e90e38b71c9af0303522c104226a68888b`;
claude-cli 2.1.220; capability_ok=true; verdict=findings;
2026-07-31T19:52:01Z.

- Confirmed the physical switch layout itself matches the canonical CB04
  Keymap and the firmware LED map.
- Confirmed the 40×5 display remains correct in the reviewed implementation.
- Identified the missing target-selection guard and supplied a concrete
  regression that left the prior 127-test web suite green.
- Ran all 127 web tests successfully. A hook-rewritten `rtk git` spelling and
  two Grep attempts against temporary files were denied, but allowed repository
  reads, git inspection, and the test command completed the capability proof.

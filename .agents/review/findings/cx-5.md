# cx-5: Neon key assignment loses keyboard focus after asynchronous validation

**Severity**: LOW — keyboard/assistive-technology users lose focus when Neon validation outlasts one animation frame; pointer users unaffected.
**Status**: Open
**Branch**: —
**Commit**: (pending)

## Evidence
For Neon devices `assignSelected` awaits server validation (`am_configurator/web/app.js:2043-2046`) then rerenders via `mutate` (line 2053). The palette click handler does not await and schedules `restoreFocus` immediately (lines 2057-2059); `restoreFocus` runs on the next animation frame (lines 788-789), so the later rerender destroys the focused node. `tests/web/app_shell.test.js:110-115` only asserts the call text exists. Trigger: palette activation on a Neon device with validation slower than one frame.

## Predicted observable failure
Focus lands on the pre-validation DOM and is destroyed by the post-validation rerender, leaving no focused element; the source-only test passes regardless.

## What
Focus restoration races the async Neon validation rerender.

## Approach
(pending)

## Files changed
(pending)

## Guard proof
(pending)

## Coder dispute (if any)

## Known gaps

## Reviewer comments
Raised by: Reviewer: codex / gpt-5.6-sol / high / standard, escalated: T1 — generation pass over 0271213487979a50641d41e614a63f9f3ed38076..3830e8489ef10c0259ac6925bf1e0ecdf75bb0d3.

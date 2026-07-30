# cx-5: Neon key assignment loses keyboard focus after asynchronous validation

**Severity**: LOW — keyboard/assistive-technology users lose focus when Neon validation outlasts one animation frame; pointer users unaffected.
**Status**: Verified
**Branch**: —
**Commit**: `b360d77`

## Evidence
For Neon devices `assignSelected` awaits server validation (`am_configurator/web/app.js:2043-2046`) then rerenders via `mutate` (line 2053). The palette click handler did not await and scheduled `restoreFocus` immediately; `restoreFocus` runs on the next animation frame, so the post-validation rerender destroyed the focused node. `tests/web/app_shell.test.js` only asserted the call text existed. Trigger: palette activation on a Neon device with validation slower than one frame.

## Predicted observable failure
Focus lands on the pre-validation DOM and is destroyed by the post-validation rerender, leaving no focused element; the source-only test passes regardless.

## What
Focus restoration raced the async Neon validation rerender.

## Approach
The palette click handler is now `async` and `await`s `assignSelected(...)` before calling `restoreFocus`, so restoration always targets the post-mutation DOM (non-Neon paths render synchronously inside the same await and behave identically).

## Files changed
- `am_configurator/web/app.js` — palette handler awaits assignment before focus restore
- `tests/web/app_shell.test.js` — guard regex requires the async/await ordering

## Guard proof
- `tests/web/app_shell.test.js` "palette picks apply to the selected key immediately" — reverting to the un-awaited handler FAILS; restoring passes 125/125 web tests.

## Coder dispute (if any)

## Known gaps
The node harness has no DOM, so the ordering is guarded at source level; a DOM-level focus test would require a browser harness the repo does not have.

## Reviewer comments
Raised by: Reviewer: codex / gpt-5.6-sol / high / standard, escalated: T1 — generation pass over 0271213487979a50641d41e614a63f9f3ed38076..3830e8489ef10c0259ac6925bf1e0ecdf75bb0d3.

Reviewer: codex / gpt-5.6-sol / high / standard
codex-cli 0.146.0; reviewed b360d775f6abefb920a9761cc90f1174654a4fea base 6636be700c7790adb2a3e6fdebf4af8d443cf6a1; guard_confirmed=true; verdict=accepted; 2026-07-30T05:58:39Z; comments: none.

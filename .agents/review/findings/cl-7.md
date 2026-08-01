# cl-7: Synthetic native drag cannot satisfy mandatory pointer capture

**Severity**: HIGH — the planned frozen WebView2 audit would throw on its first
synthetic pointerdown, leaving no dependency-free way to prove the required
Windows-first drag behavior.
**Status**: In progress
**Branch**: —
**Commit**: `bfc84cc4a664a0c28f92949ae9844e0799319407`

## Evidence
At reviewed head `8b411abfab7cb5966d4c7e4ff413f14a4cc5fc57`,
`docs/superpowers/plans/2026-08-01-imported-media-framing-repair.md:134`
made primary-pointer capture mandatory, while the native audit at lines
`287-299` could inject input only through the real DOM without Playwright,
Computer Use, or another dependency.

Current `am_configurator/web/app.js:3090-3093` calls
`stage.setPointerCapture(event.pointerId)` from the pointerdown handler.
Chromium/WebView2 rejects a pointer ID that was created only by
`new PointerEvent(...)` plus `dispatchEvent(...)`: it is not a UA-tracked
active pointer, so `setPointerCapture` raises `NotFoundError`.

## Predicted observable failure
The exact source/frozen WebView2 audit aborts on its first synthetic
pointerdown. It cannot assert immediate drag feedback or a clean console, so
the Windows-first qualification path is impossible without adding one of the
dependencies or external input mechanisms the plan prohibits.

## What
The plan required successful pointer capture and simultaneously required an
untrusted DOM-injected audit. Those requirements are incompatible in WebView2
unless capture failure for a synthetic pointer is a deliberate, tested path.

## Approach
Make capture best-effort without weakening the real pointer path. A
pointerdown installs a stage-scoped session for one pointer ID, attempts
capture, and continues only when the capture failure is specifically
`NotFoundError`. The same stage-scoped move/release path accepts untrusted audit
events, cleans itself up, and never falls back to document-global mouse
listeners. IMF-2 must guard a fake capture failure; IMF-3 must exercise it in
the native renderer.

## Files changed
- `docs/superpowers/plans/2026-08-01-imported-media-framing-repair.md` — make
  synthetic capture failure an explicit, testable interaction contract.
- `.agents/review/findings/cl-7.md` — finding and correction record.
- `.agents/review/index.md` — active finding status.
- `.agents/review/outcomes.md` — whole-change review outcome.
- `.agents/state.md` — active review-loop pointer.

## Guard proof
This is a plan-only correction; no shipped handler exists yet to execute.
The reviewed base requires capture but provides no `NotFoundError` path. The
corrected plan requires a stage-scoped fallback, acceptance of untrusted audit
events, a Node guard whose capture method throws `NotFoundError`, and the
corresponding real WebView2 sequence. `git diff --check` and the focused
release-record tests must remain green.

## Coder dispute (if any)

## Known gaps
Implementation remains blocked on owner approval of the repair plan.

## Reviewer comments
Raised by: Reviewer: claude / claude-opus-5 / high / standard (inline,
session-only; job `fable-review`) — generation pass over
`c2f6fcedb98e33d7406eace3c3af4ed53d59ffb7..8b411abfab7cb5966d4c7e4ff413f14a4cc5fc57`;
claude-cli 2.1.220; capability_ok=true; verdict=findings; exit 0; no stderr;
2026-08-01T09:03:02Z.

- The transcript model key and canonical model are both `claude-opus-5`.
- The reviewer predicted WebView2's `InvalidPointerId` / `NotFoundError`
  failure and supplied the stage-scoped, no-new-dependency correction.
- A hook-rewritten `rtk git` command and several Grep/rg forms were denied; the
  reviewer recovered with allowed repository reads and git inspection.
- The outer PTK caller timed out at 300 seconds, but the original child stayed
  alive and its persisted schema-enforced result completed after 8 minutes
  21 seconds. No review was rerun or resubmitted.

Reopened by: Reviewer: claude / claude-opus-5 / xhigh / frontier
(inline, session-only; job `fable-review`; escalated: T2) — claude-cli
2.1.220; reviewed `bfc84cc4a664a0c28f92949ae9844e0799319407`; base
`8b411abfab7cb5966d4c7e4ff413f14a4cc5fc57`; guard_confirmed=true;
capability_ok=true; verdict=reopened; exit 0; no stderr;
2026-08-01T09:16:30Z.

- The pointer-capture correction itself is valid and closes `cl-7`: the
  reviewer independently reproduced the base contradiction and confirmed all
  six required elements of the corrected contract.
- The declared five-file set is exact and `git diff --check` passes.
- A disposable worktree at the reviewed SHA passed all 68 focused packaging
  and README tests with two expected skips, then was removed and pruned.
- Reopen reason: `.agents/review/outcomes.md` and `.agents/state.md` call
  `cl-8` and `cl-9` admitted, but the reviewed index has no row or finding
  record for either. A cold session could therefore lose both after `cl-7`
  closes. Repair by registering them or by keeping them queued as candidates
  until their one-at-a-time intake.
- Non-blocking observation: `dispatchEvent()` reports an event-listener
  exception rather than rethrowing it to the caller, but the clean-console
  assertion and drag-session behavior still fail, so the finding and severity
  stand.
- Non-blocking observation: the corrected contract omits the base's explicit
  pressed-button-loss release case. Successful capture makes pointer up,
  cancel, and lost capture sufficient; the reviewer did not treat this as a
  defect.
- No review was retried or resubmitted.

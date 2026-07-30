# cx-3: A completed model refresh can populate inventory from the previous Ollama origin

**Severity**: LOW — needs a slow refresh raced against an origin save; result is stale inventory and a failing setup test, recoverable by refreshing again.
**Status**: Verified
**Branch**: —
**Commit**: `6636be7` (fix), `63bc853` (guard repair)

## Evidence
Saving a new origin clears inventory at `am_configurator/web/app.js:4376-4378`, but an already-running refresh assigned its result unconditionally (lines 4408-4415); only the Refresh button is disabled while loading (line 4280); selection then posts the displayed identity (lines 4420-4424). Trigger: start a slow refresh against origin A, save origin B, let A's request complete.

## Predicted observable failure
Origin A's models render as if they belong to origin B; selecting one persists A's model identity against B and Test setup fails until a fresh refresh.

## What
The refresh completion handler lacked an origin/epoch identity check, so a stale response overwrote the cleared inventory.

## Approach
Added `state.ollamaInventoryEpoch` (the repo's existing epoch idiom, cf. `keyAssignmentEpoch`, `mediaRenderEpoch`). `saveOllamaBaseUrl` increments it when a new origin is persisted; `refreshOllamaModels` captures the epoch at start and discards both success and failure results when the epoch has moved.

## Files changed
- `am_configurator/web/app.js` — epoch capture/increment/discard in the refresh path
- `tests/web/lighting_flow.test.js` — new "stale model refresh" guard

## Guard proof
- `tests/web/lighting_flow.test.js` "a stale model refresh cannot fill inventory from a previous origin" — removing the `if(epoch!==state.ollamaInventoryEpoch)return;` discard lines (both occurrences) FAILS the guard; restoring passes 125/125.

## Coder dispute (if any)

## Known gaps
Source-level guard; the race itself is not executed in the node harness.

## Reviewer comments
Raised by: Reviewer: codex / gpt-5.6-sol / high / standard, escalated: T1 — generation pass over 0271213487979a50641d41e614a63f9f3ed38076..3830e8489ef10c0259ac6925bf1e0ecdf75bb0d3.

Round 1 - Reviewer: codex / gpt-5.6-sol / high / standard
codex-cli 0.146.0; reviewed 6636be700c7790adb2a3e6fdebf4af8d443cf6a1 base 09de26b255844c36822cc07f3668bf92f33c8b9b; guard_confirmed=false; verdict=reopened; comments: (1) guard accepted either epoch check anywhere in refreshOllamaModels - vacuous if only the success-path discard is removed; (2) transport: git worktree add denied on .git/worktrees, proof not reproducible that round.

Round 2 (repair-delta, fresh session; T5 ceiling deviation per the recorded no-stronger-tier precedent - owner-named pair reused) - Reviewer: codex / gpt-5.6-sol / high / standard, escalated: T5 (ceiling)
codex-cli 0.146.0; reviewed 63bc853dd61d3350adcb8e294bbefbfad1b3b788 base 6636be700c7790adb2a3e6fdebf4af8d443cf6a1; guard_confirmed=true; verdict=accepted; 2026-07-30T05:54:09Z; comments: both branch-specific guard mutations failed with the required assertion messages; restoration passed all 13 focused tests; no adjacent regression in the repair surface.

# cx-3: A completed model refresh can populate inventory from the previous Ollama origin

**Severity**: LOW — needs a slow refresh raced against an origin save; result is stale inventory and a failing setup test, recoverable by refreshing again.
**Status**: Open
**Branch**: —
**Commit**: (pending)

## Evidence
Saving a new origin clears inventory at `am_configurator/web/app.js:4376-4378`, but an already-running refresh assigns its result unconditionally at lines 4408-4415; only the Refresh button is disabled while loading (line 4280), Save server remains usable; selection then posts the displayed identity at lines 4420-4424. Trigger: start a slow refresh against origin A, save origin B, let A's request complete.

## Predicted observable failure
Origin A's models render as if they belong to origin B; selecting one persists A's model identity against B and Test setup fails until a fresh refresh.

## What
The refresh completion handler lacks an origin/epoch identity check, so a stale response overwrites the cleared inventory.

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

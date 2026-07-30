# cx-2: Library Apply paths omit the required destination and hardware-write guidance

**Severity**: MEDIUM — violates the owner's settled P3 acceptance contract (every Apply names slot/document and the Write next action), recreating the release-blocking "did anything reach the keyboard?" ambiguity on the Library paths.
**Status**: Open
**Branch**: —
**Commit**: (pending)

## Evidence
Contract: `.agents/state.md` (owner UX finding bullet). `applyLibraryGenerated` emits a custom-slot message without document target or Write action at `am_configurator/web/app.js:1575-1578`; `applyLibraryLighting` names neither slot nor target nor Write action at lines 1790-1794. The guard at `tests/web/lighting_flow.test.js:135-141` enumerates only four apply functions, so both Library paths are unguarded. Trigger: apply saved generated lighting or a saved lighting composition from Library.

## Predicted observable failure
After a Library Apply, the user cannot tell which document target changed or that Write to <device> is the next step; the existing source assertion still passes.

## What
The shared `lightingAppliedDetail`/`writeActionLabel` feedback was applied to the four Studio apply paths but not to the two Library apply paths, and the guard's enumeration hid the gap.

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

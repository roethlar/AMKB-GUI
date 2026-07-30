# cx-2: Library Apply paths omit the required destination and hardware-write guidance

**Severity**: MEDIUM — violates the owner's settled P3 acceptance contract (every Apply names slot/document and the Write next action), recreating the release-blocking "did anything reach the keyboard?" ambiguity on the Library paths.
**Status**: Verified
**Branch**: —
**Commit**: `e3d46dd`

## Evidence
Contract: `.agents/state.md` (owner UX finding bullet). `applyLibraryGenerated` emitted a custom-slot message without the document target or Write action (`am_configurator/web/app.js:1575-1578`); `applyLibraryLighting` named neither slot nor target nor Write action (lines 1790-1794). The guard at `tests/web/lighting_flow.test.js:135-141` enumerated only four apply functions. Trigger: apply saved generated lighting or a saved lighting composition from Library.

## Predicted observable failure
After a Library Apply, the user cannot tell which document target changed or that Write to <device> is the next step; the existing source assertion still passes.

## What
The shared `lightingAppliedDetail`/`writeActionLabel` feedback covered the four Studio apply paths but not the two Library apply paths, and the guard's enumeration hid the gap.

## Approach
Both Library success toasts now route through `lightingAppliedDetail(slot, target, extra)`: `applyLibraryGenerated` uses `(state.ledSlot, state.ledTarget, "This effect stays saved in Library.")` and `applyLibraryLighting` uses `(state.ledSlot, destination.target, "The Library copy is unchanged.")`. The enumeration guard now includes both functions.

## Files changed
- `am_configurator/web/app.js` — both Library apply toasts use the shared helper
- `tests/web/lighting_flow.test.js` — enumeration extended to six apply paths

## Guard proof
- `tests/web/lighting_flow.test.js` "every apply path routes through the one helper" — reverting `applyLibraryLighting` to its old literal message FAILS with "applyLibraryLighting must report where the work went"; restoring passes 124/124.

## Coder dispute (if any)

## Known gaps
The enumeration guard remains source-level; a rendered-message behavioral test would be stronger.

## Reviewer comments
Raised by: Reviewer: codex / gpt-5.6-sol / high / standard, escalated: T1 — generation pass over 0271213487979a50641d41e614a63f9f3ed38076..3830e8489ef10c0259ac6925bf1e0ecdf75bb0d3.

Reviewer: codex / gpt-5.6-sol / high / standard
codex-cli 0.146.0; reviewed e3d46dd7a8070d0386f4a2420adf10fd51a38e36 base 1bb4a212a874dbf2d2436077072cb5a9048d1733; guard_confirmed=true; verdict=accepted; 2026-07-30T05:36:17Z; comments: none.

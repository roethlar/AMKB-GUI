# cl-8: Geometry limits can exceed the version-1 offset schema

**Severity**: MEDIUM — maximum-scale framing can produce an offset that the
unchanged browser and backend schema reject, breaking Preview or persistence.
**Status**: In progress
**Branch**: —
**Commit**: pending

## Evidence
At reviewed head `8b411abfab7cb5966d4c7e4ff413f14a4cc5fc57`,
`docs/superpowers/plans/2026-08-01-imported-media-framing-repair.md:79-90`
derives each legal offset limit solely from rendered and destination geometry.
For a same-size source and destination at the supported maximum scale 32, the
formula yields `(32D - D) / (2D) = 15.5` on each axis.

The unchanged version-1 validators cap offsets at 8:
`am_configurator/media_composition.py:26,386-389` uses
`MAX_TRANSFORM_OFFSET = 8.0`, and
`am_configurator/web/lighting_composer.js:36-37,78-88` uses
`MAX_OFFSET = 8` while allowing scale 32.

## Predicted observable failure
Repeated pointer or keyboard pan at scale 32 can be clamped to a
geometry-derived value above 8 and returned as a canonical version-1
transform. The next browser or backend validation rejects that transform, so
Preview, save, or Move & zoom construction fails instead of rendering the
framing state.

## What
The plan calls the geometry helper's result a canonical version-1 transform
but does not intersect its derived limits with the schema's unchanged ±8
offset range.

## Approach
Define the contract's `MAX_OFFSET` as the unchanged schema bound and cap each
per-target geometry limit by it before clamping or intersecting offsets. Add a
shared scale-32 vector whose raw geometry limit is 15.5 but whose canonical
limit is exactly 8 and whose returned offsets remain within ±8 in both
runtimes.

## Files changed
- `docs/superpowers/plans/2026-08-01-imported-media-framing-repair.md` — cap
  geometry limits by the version-1 schema and require a max-scale vector.
- `.agents/review/findings/cl-8.md` — finding and correction record.
- `.agents/review/index.md` — active finding status.
- `.agents/review/outcomes.md` — advance the qualified candidate through
  one-at-a-time intake.
- `.agents/state.md` — active review-loop pointer.

## Guard proof
This is a plan-only correction. Under the reviewed formula, a same-size
source/destination at scale 32 yields `max_x = max_y = 15.5`, which exceeds
both unchanged validators. Under the corrected formula,
`min(8, 15.5) = 8`; the shared-vector requirement makes both implementations
prove that bound. `git diff --check` and the focused release-record tests must
remain green.

## Coder dispute (if any)

## Known gaps
Implementation remains blocked on owner approval of the repair plan.
Qualified review candidate `cl-9` remains queued for its own intake, record,
fix, and verdict after `cl-8` closes.

## Reviewer comments
Raised by: Reviewer: claude / claude-opus-5 / high / standard (inline,
session-only; job `fable-review`) — generation pass over
`c2f6fcedb98e33d7406eace3c3af4ed53d59ffb7..8b411abfab7cb5966d4c7e4ff413f14a4cc5fc57`;
claude-cli 2.1.220; capability_ok=true; verdict=findings; exit 0; no stderr;
2026-08-01T09:03:02Z.

- The reviewer identified the exact version-1 ±8 mismatch at high zoom and
  recommended intersecting geometry limits with the existing schema bound.
- The outer PTK caller timed out at 300 seconds, but the original child stayed
  alive and its persisted schema-enforced result completed after 8 minutes
  21 seconds. No review was rerun or resubmitted.

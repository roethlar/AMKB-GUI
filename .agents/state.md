# Repository State

## Now

- As of `419b797`, GitHub Release `v0.1.65` has been pulled back to a draft;
  its tag and assets remain retained. Do not republish without an explicit
  owner go.
- The committed README lighting refresh (`419b797`) is rejected in part: the
  lighting image is unhelpful, and the Macro image contains real macro data.
  Screenshot work is incomplete; do not resume it without the owner asking.
  Its `lighting.png` is 1203x768 instead of release-sized 1600x1000, so
  `test_public_screenshots_are_release_sized_and_metadata_free` fails on the
  committed tree — pre-existing, unrelated to macro work.
- Macro repair: the three-mode editor is implemented and pushed. Plan
  `f13d219`; slices `4c1884d` (compiler timing: fast/slow/natural with WPM,
  cadence capture, seeded stagger), `92aad3c` (Text entry mode + JS compiler
  inverse decode), `b7f1c39` (Flow mode rows with key/down-up/pause +
  timing-scale), `b3b22c3` (Repeat mode with per-family cost quote), and
  review fix `b9f226e` (Flow is the sole event editor — the Advanced
  disclosure is gone; remove and capacity moved into Flow; decode widened so
  hand-recorded text opens in Text entry; README Macros section matches).
  Full verification green except the pre-existing lighting.png failure.
  Awaiting owner review in the app. The owner confirmed 2026-08-03 that his
  real 0 ms-delay macros work fine in practice; no zero-delay warning or
  re-timing prompt is wanted.
- A read-only static audit found six redundant labels: the QWERTY-picker
  caption, the Macros eyebrow, and four duplicate dialog/screen eyebrows.
  No audit edits were made.

## Next

- Owner reviews the reworked Macro editor (run the app, open Macros). If it
  satisfies the outcome, the remaining repair items are the deferred README
  screenshots (owner-gated) and the republish decision (explicit owner go).

## Blockers

- No external blocker. README screenshots and the `v0.1.65` republish await
  the owner.

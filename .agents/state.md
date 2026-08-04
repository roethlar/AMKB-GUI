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

- Release `0.1.66` is in preparation. Done: macro editor rework, synthetic
  README screenshots (`9e714de`), version bump (`777da50`), suite
  fully green. Remaining per the draft plan
  `docs/superpowers/plans/2026-08-03-public-release-0.1.66.md` (owner review):
  R66-1 JPEG import (owner-mandated 2026-08-02), R66-2 experimental ARM64 CI,
  R66-3 release packet, R66-4 qualification, R66-5 publication gates. Each
  publish action (tag, Release, draft disposition, Reddit) needs an explicit
  owner go. R66-1 landed as `aa1c263`. Next: R66-2 ARM64 CI jobs; the
  win-arm-vm credential needs the owner for local testing (see
  `.agents/machines.md`).

## Blockers

- No external blocker. README screenshots and the `v0.1.65` republish await
  the owner.

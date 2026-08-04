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
- Macro repair: after four rejected shapes (rows, chips, phrase/stone
  script, token flow), the owner designed the editor in chat as **three
  modes** and said go: mode 1 text entry (text box + fast/slow/natural
  timing), mode 2 flow (one row per event with key + explicit down/up +
  timing; record into rows; recorded rows editable), mode 3 repeat (N× at an
  interval with a per-family cost quote, capacity pre-checked). Plan
  `f13d219` records the agreed design. The earlier in-place-rows
  implementation (`5b723ff`) is superseded and will be replaced. Next:
  consolidated mock, then implementation on the owner's go.
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

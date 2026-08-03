# Repository State

## Now

- As of `419b797`, GitHub Release `v0.1.65` has been pulled back to a draft;
  its tag and assets remain retained. Do not republish without an explicit
  owner go.
- The committed README lighting refresh (`419b797`) is rejected in part: the
  lighting image is unhelpful, and the Macro image contains real macro data.
  Screenshot work is incomplete; do not resume it without the owner asking.
- Macro-page repair is in flight and uncommitted: `app.js`, `style.css`,
  `tests/web/app_shell.test.js`, and
  `docs/superpowers/plans/2026-08-03-macro-sequence-visibility.md` introduce
  a visible, read-only Sequence display. Targeted and browser tests passed,
  but this does not satisfy the owner: direct editing of an existing key event
  or its following delay is still hidden behind the `Edit individual events`
  disclosure. The visible sequence itself is display-only.
- A read-only static audit found six redundant labels: the QWERTY-picker
  caption, the Macros eyebrow, and four duplicate dialog/screen eyebrows.
  No audit edits were made.

## Next

- Revise the Macro-page plan and implementation so its main Sequence is an
  always-visible direct editor: edit the event key, press/release state, and
  following delay in place. Keep advanced capabilities secondary rather than
  making them the only editing surface. Resume only on the owner's go.

## Blockers

- No external blocker. The direct-editing macro repair awaits resumption.

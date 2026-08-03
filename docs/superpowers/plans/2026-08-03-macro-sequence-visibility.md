# Macro Sequence Visibility Repair

**Status:** In progress. `v0.1.65` was withdrawn to a GitHub draft on
2026-08-03 pending this repair. Revised the same day after the owner rejected
the display-only Sequence: the always-visible Sequence is the direct editor.
Its layout is a compact wrapping flow of event chips: the owner rejected a
one-row-per-event list as unusable for long macros.

## Owner outcome

The Macros screen must show the selected macro's actual sequence without an
extra click, and that always-visible Sequence is the direct editor: change an
event's key, its press/release state, and the pause that follows it in place.
The normal view must make key state and timing legible: uppercase and
lowercase must not collapse to the same display, and every pause must say
when it occurs and how long it lasts. Advanced capabilities — adding or
removing events and the capacity meter — stay secondary rather than being the
only editing surface. The public README must use only synthetic macro data in
any Macro screenshot.

## Scope

- Keep the existing macro event schema, record path, text compiler, capacity
  validation, device write boundary, and Advanced event disclosure.
- The always-visible Sequence edits in place: the sequence is a compact
  wrapping flow of chips, one per event, each carrying a press/release
  toggle, a key picker for standard keyboard keys, and the following pause
  in milliseconds, alongside the replay projection label.
- Events outside the standard key list stay plainly labelled with no fake
  picker; malformed events are never silently rewritten to a guessed key.
- Render modifier-held character runs unambiguously, including Shift-held
  uppercase and punctuation; never infer case from a key usage alone.
- Describe each inter-event pause in milliseconds at the point it occurs.
- Adding/removing events and the capacity meter remain under the Advanced
  disclosure; the Advanced editor's existing rows stay as they are.
- README screenshot replacement is deferred: it resumes only when the owner
  asks, and then uses a synthetic profile with no owner macro content.

## Implementation and proof

1. Keep the pure macro-sequence projection helper in `app.js` that consumes
   the canonical events and delays, tracks held modifiers, and emits
   accessible display tokens and pause descriptions.
2. Render the projection in the normal Macro editor as a compact wrapping
   flow of editable event chips that reuse the existing `data-action` /
   `data-event-key` / `data-delay` mutation bindings; non-standard and
   malformed events render as plainly labelled text without a picker or
   state toggle.
3. Add browser guards for lowercase, Shift-uppercase, modifier combinations,
   key-up ordering, zero/nonzero delays, in-place editing controls, and
   plainly labelled non-standard events. Keep existing Advanced-editor tests
   as preservation guards.
4. Run the full repository verification entry point, then commit the plan and
   the implementation as separate slices.
5. Rebuild and re-publish only on an explicit owner go; README screenshots
   remain deferred as scoped above.

## Non-goals

- No keyboard write, device read, release publication, CI expansion,
  lighting redesign, or README/screenshot capture in this repair.

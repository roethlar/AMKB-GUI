# Macro Sequence Editor Rework — Three Modes

**Status:** In progress. `v0.1.65` was withdrawn to a GitHub draft on
2026-08-03 pending this repair. The design was agreed with the owner through
same-day review iterations (event rows → chips → phrase/stone script → token
flow → plain-language steps → three modes). This revision records the agreed
design; it supersedes every earlier shape described in this file's history.

## Owner outcome

Every macro is edited in an always-visible direct editor — no disclosure
hides normal editing. The editor is coherent, simple to understand, and
provides all the macro functionality the keyboards support. A person must be
able to look at a macro and immediately say what it does.

## The three modes

Mode is per macro. Mode 1 is offered only when the macro is clean text (or
empty); mode 2 displays anything the device can express. Both modes are the
editor — there is no separate read view.

### Mode 1 — text entry

- The macro is a text box plus one timing choice.
- Timing: **fast** (uniform 10 ms between keys), **slow** (uniform ~100 ms),
  or **natural** — staggered like real typing, by a WPM target
  (interval = 60000 ÷ (5 × WPM)), a captured cadence (the user types a sample
  sentence once; its rhythm is reused), or seeded deterministic stagger.
- Natural variants bake to ordinary per-event delays at compile time; the
  device replays numbers and never knows the difference. The stagger is
  seeded and deterministic so it regenerates identically and stays testable.
- Compilation goes through the existing `/api/macros/text` path, extended
  with a timing spec; capacity is pre-checked exactly as today.

### Mode 2 — flow

- One row per event, and every row carries the full split: key picker,
  explicit **down/up**, and its following delay (0–15000 ms).
- Record keys captures into these same rows; recorded rows are editable in
  place (key, down/up, timing).
- Combos such as Ctrl+Alt+Del are built event by event
  (Ctrl down, Alt down, Del down, Del up, Alt up, Ctrl up) or recorded.
- Media/system (consumer page) keys join the flow-mode key picker; the
  devices already accept them in macros.
- Non-standard and malformed events stay plainly labelled, never guessed.

### Mode 3 — repeat

- Repeat a step (or selected run) N times at a fixed interval — turbo and
  loop authoring that hand-building and recording cannot serve.
- The cost is quoted before applying, in the family's own units, and the
  apply is capacity pre-checked: events on the serial boards, bytes on the
  Neon 80. Nothing partially writes.

## Also in scope

- A timing-scale action on a macro (multiply every delay once, e.g. half as
  fast), clamped to the legal delay range.
- The Advanced disclosure is retained for add/remove anywhere and the
  capacity meter.
- Type text composer and Record keys remain as entry points.

## Capacity truth (from the code, 2026-08-03)

- Serial families (CyberBoard, Relic 80, AFA): 32 macro tracks, **200 events
  total per profile** (`device_mapping.py` `_SERIAL_MACRO_EVENTS`).
- Neon 80 (Vial): 16 macro slots, **6677-byte buffer** measured from the
  owner's board; each key event costs 3 bytes and each nonzero delay a
  further 4 bytes (`vial_macros.py` encoder); zero delays are free.
- Shared schema caps any single macro at 200 events (`macros.py`).
- A key press is two events (down + up); its pause rides on the event, so a
  60× turbo = 120 events on serial boards, ≈600 bytes (one nonzero delay per
  rep) on the Neon 80.

## Implementation and proof

1. Extend the text compiler with the timing spec (fast/slow/natural),
   server-side, with Python tests for each variant and determinism.
2. Mode switcher and mode 1 surface in the Macro editor.
3. Mode 2 rows reusing the existing mutation bindings, with media keys in
   the picker and recording into rows.
4. Repeat with per-family cost quote and capacity pre-check; timing-scale
   action.
5. Browser guards for each mode, the repeat cost math per family, and
   preservation guards for the Advanced editor; run the full repository
   verification entry point; prove new tests guard the change by revert.
6. Commit in slices; rebuild and re-publish only on an explicit owner go.

## Non-goals

- No keyboard write, device read, release publication, CI expansion,
  lighting redesign, or README/screenshot capture in this repair.

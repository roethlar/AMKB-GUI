# or-3: `FamilySpec` models macro capacity in the wrong unit for Vial

**Severity**: MEDIUM — the `None` path the spec documents is unimplementable in
the browser as written, and the unit mismatch has no correct conversion.
**Status**: Open
**Branch**: (not started)
**Commit**: (not started)

## Evidence

- `am_configurator/device_mapping.py:180-181` — `macro_tracks: int | None` and
  `macro_events: int | None` are the only macro capacity fields.
- `am_configurator/device_mapping.py:167-168` — the comment states a Vial device
  "reports its own limits at runtime instead, so a family may carry `None` to
  mean device-reported", but Vial reports `GET_BUFFER_SIZE`, a byte count, not
  an event count.
- `am_configurator/web/app.js` — the browser consumes these as numbers with no
  null handling: the macro header renders `Up to ${macroTracks} tracks`, the
  meter computes `Math.min(100, total*100/macroEvents)`, and the guards read
  `totalMacroEvents() >= macroEvents`. With `macroEvents` null these yield
  "Up to null tracks", a meter pinned at 100%, and a limit that always trips.

## Predicted observable failure

Two failures, either of which is reachable once a Vial family is registered:

1. Converting a `GET_BUFFER_SIZE` byte budget into an event count must assume a
   per-event encoding size. Assuming too large rejects valid macro sets;
   assuming too small admits a set that overruns the device buffer on write.
2. Registering a family with `macro_tracks=None` / `macro_events=None` — the
   path the spec's own comment describes — renders a broken macro screen
   rather than an unlimited one.

## What

`FamilySpec` was given a `None` escape hatch for device-reported limits without
a consumer that can handle `None`, and in a unit that does not match what the
device actually reports.

## Approach

Not started. Model static serial event limits and an optional runtime byte
budget as distinct fields, overlay per-device discovered capacity on the family
spec rather than encoding it as absence, and size the complete macro buffer
exactly before any write.

## Files changed

Not started.

## Guard proof

Not started. A guard must assert the browser renders a coherent macro screen
for a family whose limits are device-reported, and that an oversized buffer is
refused by byte size rather than by event count.

## Coder dispute (if any)

None. The `None` field and its comment are mine, and I wrote the browser
consumers in the same change without handling the value the comment promises.

## Known gaps

The fix's shape depends on plan task N7, which is not yet implemented. The
minimum correction available now is to stop documenting a `None` contract that
nothing implements; the full capacity model belongs with N7.

## Reviewer comments

`Reviewer: codex / gpt-5.6-sol / (codex-configured default) / n/a — see
outcomes.md routing deviation`. Raised in the 2026-07-25 openreview pass over
`65a70c9..94a847a`. Verdict `findings`. Admitted at intake; the browser
consequence of the `None` path was verified by reading the consuming
expressions.

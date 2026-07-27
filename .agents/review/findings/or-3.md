# or-3: `FamilySpec` models macro capacity in the wrong unit for Vial

**Severity**: MEDIUM — the `None` path the spec documents is unimplementable in
the browser as written, and the unit mismatch has no correct conversion.
**Status**: Verified (available scope; the capacity model itself belongs to N7)
**Branch**: `neon-80-support` (worked in place, as or-1 and or-2 were)
**Commit**: see the `or-3:` commit on `neon-80-support`

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

The false contract is gone. `macro_tracks` and `macro_events` are plain `int`,
the three `is not None` guards in `validate_config` that made the ceilings
skippable are removed, and the module comment now states why a byte budget must
be a *separate* field rather than a different value for these: no conversion
between bytes and event counts is correct in either direction.

The capacity model itself is not built here — it needs `GET_BUFFER_SIZE` from a
real device, which is plan task N7. That requirement is now recorded in the
plan's N7 rather than left as a comment promising a `None` nothing implements.

## Files changed

- `am_configurator/device_mapping.py:181-193` — the comment now explains the
  unit mismatch; `macro_tracks`/`macro_events` are non-optional.
- `am_configurator/server.py:462,471,479` — the skippable guards removed.
- `docs/superpowers/plans/2026-07-25-am-neon-80-support.md` — N7 records that
  capacity is bytes, that the field is additive, and that `None` is forbidden.

## Guard proof

`tests/test_device_mapping.py::MacroCapacityIsAlwaysEnforceableTests`:

- `test_every_registered_family_declares_integer_ceilings` — reinstating the
  hatch (`_SERIAL_MACRO_TRACKS = None` plus optional fields and the guarded
  check) fails it with `AssertionError: None is not an instance of <class 'int'>`
  for every family.
- `test_validation_enforces_the_ceiling_for_every_family` — proves no family can
  silently opt out, by exceeding each one's own declared ceiling.
- The cross-language guard `BrowserSpecMirrorsPythonTests` catches it
  independently (`AssertionError: None != 32`), because the browser mirror has
  no way to express the hatch. Verified, then restored.

## Coder dispute (if any)

None. The `None` field and its comment are mine, and I wrote the browser
consumers in the same change without handling the value the comment promises.

## Known gaps

The full capacity model is **not** delivered here and remains open work in plan
task N7: querying `GET_COUNT` and `GET_BUFFER_SIZE`, overlaying discovered
capacity on the family spec, and sizing the complete macro buffer in bytes
before any write. What this finding closes is the false contract and the
skippable enforcement; what it defers is everything that needs a real device to
build against. The finding is marked Verified on that scope only.

## Reviewer comments

`Reviewer: codex / gpt-5.6-sol / (codex-configured default) / n/a — see
outcomes.md routing deviation`. Raised in the 2026-07-25 openreview pass over
`65a70c9..94a847a`. Verdict `findings`. Admitted at intake; the browser
consequence of the `None` path was verified by reading the consuming
expressions.

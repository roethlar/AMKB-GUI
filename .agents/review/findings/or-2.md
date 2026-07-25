# or-2: `blank_config` still owns a second copy of the family rules

**Severity**: HIGH — N1's stated goal was one authority for per-family limits,
and this path still hardcodes them; the observable failure is gated on N4.
**Status**: Verified
**Branch**: `neon-80-support` (worked in place, as or-1 was)
**Commit**: see the `or-2:` commit on `neon-80-support`

## Evidence

- `am_configurator/server.py:153` — `["#000000"] * 90`, a hardcoded keyframes
  track length, where `device_mapping.FamilySpec.track_colors` is now the
  authority.
- `am_configurator/server.py:163` — `["#000000"] * 24`, likewise for the edge
  track.
- `am_configurator/server.py:130-132` — `upper = device_id.upper()`,
  `product_id = "80" if upper == "AM21" else upper`, `relic = product_id == "80"`
  duplicates the family normalization `device_mapping.led_model()` owns.
- `am_configurator/server.py:2034` — the route feeds it `device.product_id`
  straight from the probe, so this runs for every device read with no stored
  profile.

## Predicted observable failure

Once a Neon 80 family is registered (plan task N4), reading a Neon with no
stored profile returns a blank profile shaped for the AM serial families —
a 90-colour keyframes track instead of the Neon's authored track sizes, and no
head track at all. The resulting workspace is invalid for the connected
keyboard.

**Verified not to be a present-day defect.** The obvious suspicion — that
`relic = product_id == "80"` misses the Relic's real `AM21` identifier — is
wrong: line 131 normalizes `AM21` to `80` first. Executing
`blank_config("AM21", …)` and `blank_config("80", …)` both produce the edge
track on every custom slot. The defect today is duplicated authority, not
misbehaviour.

## What

`blank_config` predates N1 and was not part of its cutover. It independently
decides which tracks a family authors, how long they are, and how to normalize
a product identifier — all three of which `device_mapping` now owns.

## Approach

Track lengths come from `spec.track_colors(...)`, and every authored track other
than `frames`/`keyframes` is emitted by name from `spec.authored_tracks` — so a
family authoring a track this function has never heard of still gets it, sized
correctly. (The first attempt kept the track *names* hardcoded and was reopened;
see "Reopen round 1" below, which is the current state of this fix.)

The product-identifier normalization moved to
`device_mapping.config_product_id`, which documents what it actually is: a
wire-format rule, not a family lookup. The two are genuinely different and the
distinction is now guarded — `CB04` stays `CB04` in the stored configuration
while resolving to family `CB`.

Deliberately **not** changed: the `frames` and `keyframes` keys are still
emitted for every family, and the slot rule (`index >= 5` is custom) is
unchanged. Emitting only authored tracks would drop `frames` from ALICE and
Relic blank profiles, which is a behaviour change this finding does not call
for and which the wire encoder and browser were not audited against.

## Files changed

- `am_configurator/device_mapping.py` — new `config_product_id`.
- `am_configurator/server.py:129-140` — spec lookup replaces the local
  normalization and the `relic` flag.
- `am_configurator/server.py:158,167` — track lengths from the spec.

## Guard proof

`tests/test_device_mapping.py::BlankConfigUsesFamilySpecTests`:

- `test_track_sizes_and_extra_tracks_follow_the_family` registers a synthetic
  family with a 49-colour keyframes track and an 11-colour edge track.
  Restoring the hardcoded `90` fails it with `AssertionError: 49 != 90`;
  restoring the `product_id == "80"` edge check fails it with
  `KeyError: 'spotlight_frames'`. Both verified, then restored.
- `test_shipped_families_keep_their_current_shape` is the regression guard: CB04,
  AM21, and 80 keep 90-colour key tracks, and only the Relic gets a 24-colour
  edge track.
- `test_the_stored_product_id_is_the_wire_identifier_not_the_family` pins the
  distinction the normalization move could have silently broken.

## Coder dispute (if any)

None on substance. On severity: the reviewer rated HIGH on the post-N4 failure,
which is correct as stated, but no current user can reach it. Recorded as HIGH
with the gating made explicit rather than silently downgraded.

## Known gaps

None.

## Reviewer comments

`Reviewer: codex / gpt-5.6-sol / (codex-configured default) / n/a — see
outcomes.md routing deviation`. Raised in the 2026-07-25 openreview pass over
`65a70c9..94a847a`. Verdict `findings`. Admitted at intake; the "after Neon
registration" framing was verified as accurate and the tempting stronger claim
was disproved by execution.

## Reopen round 1 — 2026-07-25

`codereview codex` over `94a847a..4ff65ee` returned **reopened**, correctly.

The first repair removed the hardcoded track *sizes* but left the hardcoded
track *names*: `blank_config` asked for `keyframes` and conditionally built
`spotlight_frames`, and never consulted `spec.authored_tracks` for anything
else. The guard was vacuous on exactly that point — it used those same two
names, so it could not have detected the gap. A Neon-shaped spec authoring
89-colour `axial` and 230-colour `head` tracks would still have produced a
90-colour `keyframes` and nothing else, which is the failure or-2 predicted.

Repair: every authored track other than `frames`/`keyframes` is now emitted by
name from the specification and sized from it. `frames` and `keyframes` remain
unconditional for every family, unchanged, because that is how these profiles
have always been shaped.

New guard: `test_tracks_the_function_never_mentions_are_still_emitted`
registers a family authoring `axial` and `head` — names the implementation has
never heard of — and asserts both appear on custom slots at 89 and 230 colours,
and on no other slot. Narrowing the comprehension back to `spotlight_frames`
fails it with `KeyError: 'axial'`. Verified, then restored.

Verification after repair: 411 tests OK (skipped=1), compileall clean, 48 node
tests pass.

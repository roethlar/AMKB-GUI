# or-2: `blank_config` still owns a second copy of the family rules

**Severity**: HIGH — N1's stated goal was one authority for per-family limits,
and this path still hardcodes them; the observable failure is gated on N4.
**Status**: Open
**Branch**: (not started)
**Commit**: (not started)

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

Not started. Derive the authored tracks and their lengths from
`device_mapping.spec_for_product(device_id)`, and keep the slot rules
(`index >= 5` is custom) explicit rather than folded into the family check.

## Files changed

Not started.

## Guard proof

Not started. Per the N1a precedent, a guard written against the shipped
families would be vacuous — they share the same track sizes. It must register a
synthetic family with two differing track sizes and assert `blank_config`
follows it.

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

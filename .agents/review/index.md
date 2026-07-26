# Review status

Workflow: see `.agents/playbooks/codereview.md`.
Per-finding detail: see `.agents/review/findings/<id>.md`.
Whole-change pass records: see `.agents/review/outcomes.md`.

## Legend
- `[ ]` Admitted, open (passed intake triage; not yet started)
- `[~]` In progress / pending review
- `[x]` Verified (awaiting owner-gated merge)
- `[!]` Contested — declined, disputed, or ruled invalid; awaiting owner adjudication
- `[-]` Declined at intake (kept for the record; no work)

## Findings

| ID   | Severity | Impact (one line)                                                        | Status | Branch | Reviewer          |
|------|----------|--------------------------------------------------------------------------|--------|--------|-------------------|
| or-1 | HIGH     | HID driver cannot build its protocol from pre-encoded AM serial frames    | `[x]`  | `neon-80-support` | codex/openreview  |
| or-2 | HIGH     | `blank_config` hardcodes family track sizes N1 made `device_mapping` own  | `[x]`  | `neon-80-support` | codex/openreview  |
| or-3 | MEDIUM   | `FamilySpec` macro capacity uses event counts; Vial reports bytes         | `[x]`  | `neon-80-support` | codex/openreview  |
| n3-1 | HIGH     | Vial UID is per-model, not per-unit; two Neons collide on one address     | `[x]`  | `neon-80-support` | codex/openreview  |
| n3-2 | HIGH     | `HidSession` writes without requiring a `WriteApproval`                   | `[x]`  | `neon-80-support` | codex/openreview  |
| n3-3 | HIGH     | udev rule ships only in the sdist; wheel and AppImage users cannot get it | `[x]`  | `neon-80-support` | codex/openreview  |
| n3-4 | MEDIUM   | hidapi reports every open failure as `open failed`; udev remedy unreachable | `[x]` | `neon-80-support` | codex/openreview  |
| n3-5 | MEDIUM   | No decompressed-size bound on device-supplied XZ definition               | `[x]`  | `neon-80-support` | codex/openreview  |
| n4-1 | HIGH     | `sudo app > /etc/...` cannot write; the documented remedy always fails    | `[x]`  | `neon-80-support` | codex/openreview  |
| n4-2 | MEDIUM   | Neon editor renders an invented identity layout before geometry loads    | `[x]`  | `neon-80-support` | codex/openreview  |
| n567-1 | HIGH     | Neon device reads cannot produce a valid API response                  | `[x]`  | `neon-80-support` | codex/openreview  |
| n567-2 | HIGH     | Shared validation rejects every native Neon keymap                     | `[x]`  | `neon-80-support` | codex/openreview  |
| n567-3 | HIGH     | Discovery and write confirmation use different product identifiers     | `[x]`  | `neon-80-support` | codex/openreview  |
| n567-4 | HIGH     | The enabled full-write path never transmits the keymap                 | `[x]`  | `neon-80-support` | codex/openreview  |
| n567-5 | HIGH     | Common application keycodes have no Neon translation                   | `[x]`  | `neon-80-support` | codex/openreview  |
| n567-6 | HIGH     | Vial macro encoding discards macro slot identity                       | `[x]`  | `neon-80-support` | codex/openreview  |
| n567-7 | HIGH     | A full configuration write silently ignores lighting slots 2 and 3     | `[x]`  | `neon-80-support` | codex/openreview  |
| n567-8 | HIGH     | Successful Neon writes crash before persistence                        | `[x]`  | `neon-80-support` | codex/openreview  |
| n567-9 | MEDIUM   | Device-reported macro byte capacity never reaches the editor           | `[ ]`  | `neon-80-support` | codex/openreview  |
| n567-10 | MEDIUM   | Neon keymap layout and assignment filtering were not integrated        | `[ ]`  | `neon-80-support` | codex/openreview  |

All three raised by the 2026-07-25 openreview codex pass over
`65a70c9..94a847a` and admitted at intake after independent verification of
every citation.

or-1 is fixed: the owner ruled to rework N2 immediately rather than defer to
N5, plan task N2 was revised first, and the correction landed with a guard that
fails when the seam is reverted. It has not been re-reviewed — an accepted
verdict on the repair would need a `codereview` redispatch, which the owner has
not asked for.

or-2 is fixed: blank profiles now take their track sizes and extra tracks from
the family specification, guarded by a synthetic family whose sizes differ from
every shipped one.

or-3 is closed on its available scope: the `None` macro-capacity contract and
the skippable enforcement are gone, and the byte-budget requirement moved into
plan task N7. The capacity model itself needs a real device and remains N7 work.

All three findings are fixed **and re-reviewed**. `codereview codex` over each
repair, 2026-07-25:

| Finding | Repair | Round 1 | Round 2 |
|---------|--------|---------|---------|
| or-1 | `f08fb22` | accepted | — |
| or-2 | `4ff65ee` | **reopened** | `71b9aa8` accepted |
| or-3 | `858fdf0` | accepted | — |

`guard_confirmed` was `true` on every verdict; the reviewer ran the revert /
fail / restore / pass proof in its own worktree. or-2's reopen was correct: the
first repair removed the hardcoded track sizes but left the hardcoded track
names, and its guard used those same names, so it was vacuous on the one claim
it was cited for. Detail in `.agents/review/findings/or-2.md`, "Reopen round 1".

Routing deviation is unchanged from the openreview passes and recorded in
`.agents/review/outcomes.md`: no owner-confirmed tier mapping exists on this
machine, so codex's own configured model and effort were used under the owner's
standing "defaults, just codex" direction. The T5 escalation a reopen normally
triggers therefore had no stronger tier to reach; the redispatch opened a fresh
session at the same routing, which is recorded rather than presented as an
escalation.

## N3 pass — 2026-07-25

`openreview codex` over `16901d8..abf32d7` (plan task N3) returned `findings`
with five, all admitted at intake. Three were verified empirically rather than
accepted on prose:

- n3-3: `unzip -l` on the built wheel finds the udev rule **0 times**.
- n3-4: `open_path` on a bad path raises `OSError('open failed')` — no
  `permission` or `busy` substring exists to match, so every failure is reported
  as "no longer attached".
- n3-5: 200 MiB of zeros compresses to **30,644 bytes**, which passes the 64 KiB
  compressed-size cap and then expands in full.

n3-1 and n3-2 are code-reading findings, both plain from the source. n3-1 cannot
be fully confirmed here — it needs a second Neon 80 — and its record says so.

Common thread worth stating: three of the five are guards that were written but
not made load-bearing. `WriteApproval` exists and nothing requires it; the
compressed-size cap bounds the wrong quantity; the packaging test asserts the
sdist and the artifacts that ship to users are the wheel and AppImage.

All five N3 findings are fixed, one commit each, each red-proofed by reverting
the fix and observing the named guard fail.

Two of the repairs needed a second attempt at the guard, for the same reason the
review existed: the first version tested a new helper directly and left the call
site unguarded, so reverting the call site kept every test green. n3-5 and n3-4
both record that. It is the identical non-load-bearing pattern the pass flagged,
caught this time by red-proofing rather than by a reviewer.

None of these repairs has been re-reviewed.

## N4 pass — 2026-07-25

`openreview codex` over `eb21629..179f052` returned `findings` with two, both
admitted and both fixed. n4-1 was self-inflicted by the n3-3 repair: fixing the
AppImage problem introduced a shell problem, and the guard written alongside it
only checked that the text mentioned the flag.

Its replacement guard was itself not collected — appended below the module's
`__main__` block, outside any class — so the first red-proof passed against a
deliberately broken document. Caught by noticing the suite count had not moved.

## N5-N7 pass — 2026-07-26

`openreview codex` over `6c396c9..d17c2ca` returned **ten findings, eight HIGH**,
all admitted. The pass is the most valuable one so far and the reason is worth
stating plainly.

Each protocol module — lighting, keymap, macros — is sound in isolation and well
guarded. The **seams between them and the existing application were not built**,
and unit tests over well-formed inputs could not reveal that. The plan's tasks
were implemented as units and reported complete; end to end, a user could not
have used the keyboard.

The clearest examples: `write_config` preflights the keymap and never transmits
it; only lighting slot 1 is written while slots 2 and 3 are silently skipped;
discovery and deep identification report different `product_id` values so the
typed write confirmation can never match; and a successful write raises on
`after.version` before persisting anything.

`n567-2` is a self-inflicted repeat: it is the `validate_config` gap recorded as
known open work under `or-1` and left unscheduled. Recording a gap is not
closing it.

Eight findings are repaired and red-proven on the current branch:

| Findings | Repair |
|----------|--------|
| n567-1, n567-3, n567-4, n567-7, n567-8 | `48398c9` |
| n567-2 | `8546d54` |
| n567-5 | `21c8e56` |
| n567-6 | `77ff823` |

`n567-9` remains open after `8546d54` repaired the static browser mirror but
left the connected device's reported capacity unprojected. `n567-10` remains
open. None of these repairs has been re-reviewed.

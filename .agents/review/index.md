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

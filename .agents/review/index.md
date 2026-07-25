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
| or-2 | HIGH     | `blank_config` hardcodes family track sizes N1 made `device_mapping` own  | `[ ]`  |        | codex/openreview  |
| or-3 | MEDIUM   | `FamilySpec` macro capacity uses event counts; Vial reports bytes         | `[ ]`  |        | codex/openreview  |

All three raised by the 2026-07-25 openreview codex pass over
`65a70c9..94a847a` and admitted at intake after independent verification of
every citation.

or-1 is fixed: the owner ruled to rework N2 immediately rather than defer to
N5, plan task N2 was revised first, and the correction landed with a guard that
fails when the seam is reverted. It has not been re-reviewed — an accepted
verdict on the repair would need a `codereview` redispatch, which the owner has
not asked for.

or-2 and or-3 remain open and need no ruling; both are completions of N1.

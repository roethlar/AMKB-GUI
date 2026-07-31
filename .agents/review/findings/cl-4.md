# cl-4: Repository state still reports the Node 24 upgrade as unlanded

**Severity**: MEDIUM — the canonical cold-start record sends a new session back to an already-completed approval and implementation step instead of the required remote acceptance.
**Status**: Open
**Branch**: —
**Commit**: —

## Evidence
At reviewed head `7586bf7daab187a158a5c929cafcb80f9af97d10`,
`.agents/state.md:58-63` says the workflows still use the retired Node 20
action refs and describes their upgrade as a pending draft. Lines 77-80 say
owner approval for A1 is still pending.

The same head has the reviewed Node 24 action set in
`.github/workflows/ci.yml` and `.github/workflows/desktop.yml`, with the A1
implementation committed as `7586bf7daab187a158a5c929cafcb80f9af97d10`.
The owner approved A1 and its defined A2 qualification before implementation.

## Predicted observable failure
A cold session following the mandatory startup procedure trusts
`.agents/state.md` and either requests the already-settled A1 approval again or
attempts to repeat the landed workflow edit. The actual next step, A2 remote
acceptance of the exact A1 commit, is hidden.

## What
The repository's canonical current-state entry point was not synchronized when
A1 landed.

## Approach
Replace the stale Node 20/pending-plan bullet with the exact A1 commit and its
locally verified Node 24 contract. Replace the pending-approval Next item with
A2 remote acceptance, while keeping the active-review pointer until both
record-drift findings close.

## Files changed
- `.agents/state.md` — record A1 as landed and make A2 the next action.
- `.agents/review/findings/cl-4.md` — finding and proof record.
- `.agents/review/index.md` — review-loop status.

## Guard proof
Manual record proof: at the reviewed head, the retired refs named by
`.agents/state.md` are absent from both workflows and the Node 24 guard passes,
so the state assertion is demonstrably false. After the repair, the state
record must name the exact A1 commit, preserve A2 as outstanding, and contain
no claim that A1 approval is pending.

## Coder dispute (if any)

## Known gaps
A2 remote workflow, artifact, provenance, and Windows installation acceptance
has not run. `cl-5` separately owns the stale plan Status block.

## Reviewer comments
Raised by: Reviewer: claude / claude-opus-5 / high / standard (inline,
session-only) — generation pass over
`43eae714b80322b5424efaced46a1826dfd67753..7586bf7daab187a158a5c929cafcb80f9af97d10`;
claude-cli 2.1.220; capability_ok=true; verdict=findings;
2026-07-31T04:00:31Z.

- The canonical startup record still names the retired v4/v6 refs and an open
  A1 approval gate after the reviewed head replaced them.
- Because `.agents/state.md` must stay current as work lands, deferring this
  synchronization to A2 closure creates a real false-state window.
- The initial hook-rewritten `rtk git` command was denied by the launch
  allowlist; allowed repository reads and git inspection completed the review.

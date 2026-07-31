# cl-5: Node 24 plan still reports A1 approval as pending

**Severity**: LOW — the approved implementation plan falsely presents its completed A1 gate as open, which can trigger a redundant approval request or an incorrect governance escalation.
**Status**: In progress
**Branch**: —
**Commit**: —

## Evidence
At reviewed head `7586bf7daab187a158a5c929cafcb80f9af97d10`,
`docs/superpowers/plans/2026-07-30-github-actions-node24-upgrade.md:3-6`
says A1 implementation approval remains pending.

A1.1 and A1.2 are the workflow guard and action-ref changes committed at that
head. The owner approved A1 and its defined A2 qualification before the
implementation began.

## Predicted observable failure
An implementer or auditor reading the plan treats the landed A1 commit as
unauthorized or asks the owner to approve it again. The plan conflicts with the
code and the owner's settled instruction instead of identifying A2 as the
remaining acceptance step.

## What
The plan's Status block was not advanced when its approved A1 slice landed.

## Approach
Update the Status block to record the exact A1 implementation commit and its
required Opus review outcome, while leaving A2 remote acceptance explicitly
outstanding. The detailed run IDs, artifacts, hashes, and installer outcomes
remain reserved for the A2 closure record.

## Files changed
- `docs/superpowers/plans/2026-07-30-github-actions-node24-upgrade.md`
  — advance the plan status from pending A1 approval to pending A2 acceptance.
- `.agents/review/findings/cl-5.md` — finding and proof record.
- `.agents/review/index.md` — review-loop status.
- `.agents/state.md` — next-action pointer after the finding closes.

## Guard proof
Manual record proof: the base Status block says approval is pending while
`git show 7586bf7` contains the plan's complete A1.1/A1.2 file set. The
repaired Status block names exact A1 commit
`7586bf7daab187a158a5c929cafcb80f9af97d10`, contains no pending-A1-approval
claim, and keeps A2 acceptance pending because no remote proof has been
recorded.

## Coder dispute (if any)

## Known gaps
A2 remote workflow, artifact, provenance, and Windows installation acceptance
has not run. Its evidence remains intentionally absent until observed.

## Reviewer comments
Raised by: Reviewer: claude / claude-opus-5 / high / standard (inline,
session-only) — generation pass over
`43eae714b80322b5424efaced46a1826dfd67753..7586bf7daab187a158a5c929cafcb80f9af97d10`;
claude-cli 2.1.220; capability_ok=true; verdict=findings;
2026-07-31T04:00:31Z.

- The plan's own A1.1 and A1.2 changes are present at the reviewed head, but
  its Status block still says their approval is pending.
- The detailed A2 closure evidence can remain deferred without leaving the A1
  authorization and landing status false.
- The review transcript reports the exact requested `claude-opus-5` model;
  the denied upstream WebFetch was not needed to establish this finding.

# cl-9: Canonical state duplicates the volatile nagatha address

**Severity**: LOW — an address change can leave the mandatory cold-start
record pointing agents at a stale host even when the canonical machine record
is current.
**Status**: Verified
**Branch**: —
**Commit**: `107f459852db5c5abec78187ce72548248e6ecb7`

## Evidence
At reviewed head `8b411abfab7cb5966d4c7e4ff413f14a4cc5fc57`,
`.agents/state.md:148-150` says `.agents/machines.md` owns host details and then
duplicates `nagatha`'s literal `michael@10.1.10.247` address.
`.agents/machines.md:81-88` is the canonical machine record and already carries
the current address, hostname, platform, and host-key identity.

## Predicted observable failure
When DHCP or network configuration changes `nagatha`'s address, updating the
canonical machine record alone leaves `.agents/state.md` stale. A cold session
following mandatory startup can attempt SSH to the old address and fail.

## What
The current-state entry point keeps a second copy of volatile connection data
immediately after declaring another file its sole owner.

## Approach
Remove the literal address from `.agents/state.md` and retain only a pointer
that `.agents/machines.md` owns all `nagatha` connection details. Leave the
canonical machine record unchanged.

## Files changed
- `.agents/state.md` — remove the duplicate address and keep the canonical
  pointer; advance the active review-loop state.
- `.agents/review/findings/cl-9.md` — finding and correction record.
- `.agents/review/index.md` — active finding status.
- `.agents/review/outcomes.md` — advance the final qualified candidate through
  one-at-a-time intake.

## Guard proof
This is a record-only correction. At the reviewed base, both state and machines
contain `10.1.10.247`; after the correction, the literal remains only in the
canonical machine record and state still directs cold sessions there.
`git diff --check` and the focused release-record tests must remain green.

## Coder dispute (if any)

## Known gaps
Implementation remains blocked on owner approval of the imported-media framing
repair plan. This is the last queued finding from the generation review.

## Reviewer comments
Raised by: Reviewer: claude / claude-opus-5 / high / standard (inline,
session-only; job `fable-review`) — generation pass over
`c2f6fcedb98e33d7406eace3c3af4ed53d59ffb7..8b411abfab7cb5966d4c7e4ff413f14a4cc5fc57`;
claude-cli 2.1.220; capability_ok=true; verdict=findings; exit 0; no stderr;
2026-08-01T09:03:02Z.

- The reviewer identified the duplicate immediately after state declares
  `.agents/machines.md` canonical and recommended a pointer-only state entry.
- The outer PTK caller timed out at 300 seconds, but the original child stayed
  alive and its persisted schema-enforced result completed after 8 minutes
  21 seconds. No review was rerun or resubmitted.

Accepted by: Reviewer: claude / claude-opus-5 / high / standard (inline,
session-only; job `fable-review`) — claude-cli 2.1.220; reviewed
`107f459852db5c5abec78187ce72548248e6ecb7`; base
`73600853586ad6be7d418239fb31b8863824c2b8`; guard_confirmed=true;
capability_ok=true; verdict=accepted; exit 0; no stderr;
2026-08-01T09:42:24Z.

- Independently proved the base carried exactly two tracked address copies:
  the canonical machine record and the conflicting state entry.
- Confirmed the reviewed state contains no address literal, remains
  cold-actionable through its canonical `.agents/machines.md` pointer, and
  leaves the complete machine record unchanged.
- The single commit touches exactly the declared four files and advances only
  `cl-9`'s one-at-a-time paperwork.
- A disposable worktree passed `git diff --check`, the address-owner grep, and
  all 68 focused packaging and README tests with two expected skips. It was
  removed and pruned without changing the shared tree.
- Non-blocking observation: this finding retains the literal address as pinned
  historical evidence. It is not a connection lookup and cannot create the
  stale-SSH failure; removing it would weaken the audit trail.
- The owner ruled on 2026-08-01 to salvage this completed Opus review after it
  was dispatched contrary to the requested Fable model. The result is retained
  exactly as returned; no rerun, replacement, or resubmission occurred.
